"""HTTP client for the external tag Registry service.

Auth: every request carries a Google-minted OIDC ID token (audience = REGISTRY_AUDIENCE)
so the Registry can verify calls come from this service's Cloud Run identity, plus an
X-Actor-Name header identifying who/what triggered the call on our side.

NOTE: the Registry's exact endpoint paths and request/response shapes are not available
in this repo. The paths and payloads below (GET /tags, POST /tags/{id}/status,
POST /tags/{id}/events, POST /tags/{id}/revert) are a reasonable REST convention chosen
to match the spec's method names — adjust `_request` call sites if the real Registry API
differs.
"""
import os
import time
import logging
from typing import Any, Optional

import httpx
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token as google_id_token
from jose import jwt as jose_jwt

logger = logging.getLogger(__name__)

REGISTRY_BASE_URL = os.environ.get("REGISTRY_BASE_URL", "").rstrip("/")
REGISTRY_AUDIENCE = os.environ.get("REGISTRY_AUDIENCE") or REGISTRY_BASE_URL

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
        status: Optional[str] = None,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
    ) -> Any:
        params = {
            k: v
            for k, v in {
                "q": q,
                "species": species,
                "location": location,
                "category": category,
                "status": status,
                "limit": limit,
                "cursor": cursor,
            }.items()
            if v is not None
        }
        return await self._request("GET", "/tags", actor_name, params=params)

    async def reconcile(self, actor_name: str, *, since: str) -> Any:
        """Fetches the Registry's own record of status changes since `since` (ISO date),
        for cross-checking against our local registry_sync_outbox — see registry_report.py.

        NOTE: path and response shape are an assumption (this repo has no real Registry API
        to confirm against) — adjust if the actual /api/integration/reconcile differs.
        """
        return await self._request("GET", "/api/integration/reconcile", actor_name, params={"since": since})

    async def post_status(
        self,
        actor_name: str,
        tag_id: str,
        *,
        status: str,
        source_event_id: str,
    ) -> Any:
        payload = {"status": status, "source_event_id": source_event_id}
        return await self._request("POST", f"/tags/{tag_id}/status", actor_name, json=payload)

    async def post_event(
        self,
        actor_name: str,
        tag_id: str,
        *,
        event_type: str,
        source_event_id: str,
        payload: dict,
    ) -> Any:
        body = {"event_type": event_type, "source_event_id": source_event_id, "payload": payload}
        return await self._request("POST", f"/tags/{tag_id}/events", actor_name, json=body)

    async def revert(
        self,
        actor_name: str,
        tag_id: str,
        *,
        source_event_id: str,
        previous_status: str,
    ) -> Any:
        body = {"source_event_id": source_event_id, "previous_status": previous_status}
        return await self._request("POST", f"/tags/{tag_id}/revert", actor_name, json=body)
