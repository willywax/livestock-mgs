"""Auth dependency for endpoints called by Google infrastructure (a Cloud Run
scheduler, or the Registry service itself) rather than by a logged-in ShambaManager
user.

Verifies the caller presents a Google-signed OIDC ID token (as Cloud Run's built-in
service-to-service auth mints) and that the token's `email` claim is on an allowlist
of service accounts.

Env vars:
  INTERNAL_SYNC_AUDIENCE          expected `aud` claim — this service's own Cloud Run URL.
  SYNC_ALLOWED_SERVICE_ACCOUNTS   comma-separated allowlist of caller service-account emails.
"""
import os
import logging
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

_auth_request = google_requests.Request()


def _allowed_service_accounts() -> set[str]:
    raw = os.environ.get("SYNC_ALLOWED_SERVICE_ACCOUNTS", "")
    return {email.strip() for email in raw.split(",") if email.strip()}


async def require_cloud_run_service_account(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """Verifies a Cloud Run-issued Google ID token and its allowlisted service account.

    Returns the caller's service-account email on success.
    """
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    allowed = _allowed_service_accounts()
    if not allowed:
        logger.error("SYNC_ALLOWED_SERVICE_ACCOUNTS is not configured; refusing all internal sync calls")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Internal sync is not configured")

    audience = os.environ.get("INTERNAL_SYNC_AUDIENCE")
    if not audience:
        logger.error("INTERNAL_SYNC_AUDIENCE is not configured; refusing all internal sync calls")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Internal sync is not configured")

    try:
        claims = google_id_token.verify_oauth2_token(
            credentials.credentials, _auth_request, audience=audience
        )
    except Exception as exc:
        logger.warning("Rejected internal sync call: invalid ID token (%s)", exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid ID token")

    email = claims.get("email")
    if not claims.get("email_verified") or email not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Service account not allowlisted")

    return email
