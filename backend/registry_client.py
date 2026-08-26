"""HTTP client for the external Herd Tag Registry service's integration API.

Auth: every request carries a Google-minted OIDC ID token (audience = REGISTRY_AUDIENCE)
so the Registry can verify calls come from this service's Cloud Run identity, plus an
X-Actor-Name header identifying who/what triggered the call on our side.

Paths and payload shapes below were confirmed against the real Registry's own
GET /openapi.json (fetched 2026-08-26) — not a guess. Every write call includes
source_system="ShambaManager" per its IntegrationStatusChangeRequest /
IntegrationEventLogRequest / IntegrationRevertRequest schemas.
"""
import os
import time
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token as google_id_token
from jose import jwt as jose_jwt

logger = logging.getLogger(__name__)

REGISTRY_BASE_URL = os.environ.get("REGISTRY_BASE_URL", "").rstrip("/")
REGISTRY_AUDIENCE = os.environ.get("REGISTRY_AUDIENCE") or REGISTRY_BASE_URL

SOURCE_SYSTEM = "ShambaManager"

REQUEST_TIMEOUT_SECONDS = 10.0
TOKEN_REFRESH_MARGIN_SECONDS = 300  # refresh ~5 min before expiry


class RegistryError(Exception):
    """Base class for registry_client errors."""


class RegistryConflict(RegistryError):
    """Raised on HTTP 409 — the Registry's current state disagrees with our request."""

    def __init__(self, current_status: Optional[str], detail: Any = None):
        self.current_status = current_status
        self.detail = detail
        super().__init__(f"Registry conflict: current_status={current_status!r}")


class RegistryNotFound(RegistryError):
    """Raised on HTTP 404 — the tag/resource does not exist in the Registry."""

    def __init__(self, detail: Any = None):
        self.detail = detail
        super().__init__("Registry resource not found")


class RegistryUnavailable(RegistryError):
    """Raised on timeouts, connection errors, or HTTP 5xx — safe to retry later."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"Registry unavailable: {reason}")


class RegistryAuthError(RegistryUnavailable):
    """Raised on 401/403 — the Registry rejected our credentials.

    Subclasses RegistryUnavailable so existing `except RegistryUnavailable` call sites
    keep working unchanged, but this is logged loudly (with the response body) since
    retrying alone won't fix a credentials/config problem.
    """

    def __init__(self, status_code: int, detail: Any):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"authentication rejected ({status_code}): {detail}")


class _IdTokenCache:
    """Caches a single Google-minted ID token for one audience until ~5 min before expiry."""

    def __init__(self, audience: str):
        self._audience = audience
        self._token: Optional[str] = None
        self._expiry: float = 0.0
        self._auth_request = GoogleAuthRequest()

    def get(self) -> str:
        now = time.time()
        if self._token is None or now >= self._expiry - TOKEN_REFRESH_MARGIN_SECONDS:
            if not self._audience:
                raise RuntimeError("REGISTRY_AUDIENCE (or REGISTRY_BASE_URL) is not configured")
            self._token = google_id_token.fetch_id_token(self._auth_request, self._audience)
            claims = jose_jwt.get_unverified_claims(self._token)
            self._expiry = claims.get("exp", now + 3600)
        return self._token


_token_caches: dict[str, _IdTokenCache] = {}


def _get_token_cache(audience: str) -> _IdTokenCache:
    cache = _token_caches.get(audience)
    if cache is None:
        cache = _IdTokenCache(audience)
        _token_caches[audience] = cache
    return cache


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def _iso_datetime(value) -> str:
    """The Registry's integration schemas require a full date-time, not a bare date."""
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):  # date
        return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc).isoformat()
    return str(value)


class RegistryClient:
    def __init__(self, base_url: Optional[str] = None, audience: Optional[str] = None):
        self._base_url = (base_url if base_url is not None else REGISTRY_BASE_URL).rstrip("/")
        self._audience = audience or REGISTRY_AUDIENCE
        if not self._base_url:
            raise RuntimeError("REGISTRY_BASE_URL is not configured")

    async def _request(self, method: str, path: str, actor_name: str, **kwargs) -> Any:
        token = _get_token_cache(self._audience).get()
        headers = kwargs.pop("headers", None) or {}
        headers["Authorization"] = f"Bearer {token}"
        headers["X-Actor-Name"] = actor_name

        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.request(method, path, headers=headers, **kwargs)
        except httpx.TimeoutException as exc:
            raise RegistryUnavailable(f"timeout calling {method} {path}") from exc
        except httpx.ConnectError as exc:
            raise RegistryUnavailable(f"connection error calling {method} {path}") from exc
        except httpx.HTTPError as exc:
            raise RegistryUnavailable(f"transport error calling {method} {path}: {exc}") from exc

        if response.status_code == 409:
            body = _safe_json(response) or {}
            raise RegistryConflict(current_status=body.get("current_status"), detail=body)
        if response.status_code == 404:
            raise RegistryNotFound(detail=_safe_json(response))
        if response.status_code in (401, 403):
            body = _safe_json(response)
            logger.error(
                "Registry rejected our credentials (%s) for %s %s: %s",
                response.status_code, method, path, body,
            )
            raise RegistryAuthError(response.status_code, body)
        if response.status_code >= 500:
            raise RegistryUnavailable(f"{response.status_code} from {method} {path}")

        response.raise_for_status()
        return _safe_json(response)

    async def search_tags(
        self,
        actor_name: str,
        *,
        q: Optional[str] = None,
        species: Optional[str] = None,
        location: Optional[str] = None,
        category: Optional[str] = None,
        status: Optional[list] = None,
        exclude_terminal: Optional[bool] = None,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
    ) -> Any:
        """GET /api/integration/tags -> IntegrationTagsPage {items: [IntegrationTagOut], next_cursor}.

        `status` is a list of status strings (repeated query param) per the real schema.
        `exclude_terminal` defaults true on the Registry's side when omitted (its own
        "a sold animal cannot be picked twice" behavior) — leave unset to keep that default.

        species/location/category are matched as exact-case uppercase codes on the Registry's
        side (confirmed empirically — e.g. "sheep"/"Ghutta"/"Koo" match nothing, only
        "SHEEP"/"GHUTTA"/"KOO" do), so they're uppercased here regardless of how the caller
        formats them.
        """
        species = species.upper() if species else species
        location = location.upper() if location else location
        category = category.upper() if category else category
        params = {
            k: v
            for k, v in {
                "q": q,
                "species": species,
                "location": location,
                "category": category,
                "status": status,
                "exclude_terminal": exclude_terminal,
                "limit": limit,
                "cursor": cursor,
            }.items()
            if v is not None
        }
        return await self._request("GET", "/api/integration/tags", actor_name, params=params)

    async def reconcile(self, actor_name: str, *, since: Optional[str] = None, cursor: Optional[str] = None) -> Any:
        """GET /api/integration/reconcile -> IntegrationReconcilePage {items: [IntegrationReconcileItem], next_cursor}.

        Every tag currently in a terminal status, paired with the (non-reverted) integration
        event that set it, or null when no integration event explains it.
        """
        params = {k: v for k, v in {"since": since, "cursor": cursor}.items() if v is not None}
        return await self._request("GET", "/api/integration/reconcile", actor_name, params=params)

    async def post_status(
        self,
        actor_name: str,
        tag_id: str,
        *,
        event_type: str,
        new_status: str,
        source_event_id: str,
        event_date,
        expected_current_status: Optional[str] = None,
        note: Optional[str] = None,
    ) -> Any:
        """POST /api/integration/tags/{tag_id}/status -> IntegrationStatusChangeResponse.

        `event_type` must be one of "DEATH" | "SALE" (the Registry's own enum) — distinct
        from `new_status`, the Registry's status *label* to move the tag to.
        """
        payload = {
            "source_system": SOURCE_SYSTEM,
            "source_event_id": source_event_id,
            "event_type": event_type,
            "new_status": new_status,
            "event_date": _iso_datetime(event_date),
            "expected_current_status": expected_current_status,
            "note": note,
        }
        return await self._request("POST", f"/api/integration/tags/{tag_id}/status", actor_name, json=payload)

    async def post_event(
        self,
        actor_name: str,
        tag_id: str,
        *,
        event_type: str,
        source_event_id: str,
        event_date,
        note: Optional[str] = None,
        value: Any = None,
    ) -> Any:
        """POST /api/integration/tags/{tag_id}/events -> IntegrationEventLogResponse."""
        payload = {
            "source_system": SOURCE_SYSTEM,
            "source_event_id": source_event_id,
            "event_type": event_type,
            "event_date": _iso_datetime(event_date),
            "note": note,
            "value": value,
        }
        return await self._request("POST", f"/api/integration/tags/{tag_id}/events", actor_name, json=payload)

    async def revert(self, actor_name: str, *, source_event_id: str, reason: str) -> Any:
        """POST /api/integration/events/{source_event_id}/revert -> IntegrationRevertResponse.

        Keyed by source_event_id only (not tag_id) — the Registry looks up the tag itself
        from its own stored integration event.
        """
        payload = {"source_system": SOURCE_SYSTEM, "reason": reason}
        return await self._request(
            "POST", f"/api/integration/events/{source_event_id}/revert", actor_name, json=payload
        )
