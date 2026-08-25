"""Unit tests for registry_auth.py — Google ID-token verification is mocked (no network)."""
import asyncio

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

import registry_auth


def _run(coro):
    return asyncio.run(coro)


def _creds(token="tok"):
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_missing_credentials_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        _run(registry_auth.require_cloud_run_service_account(None))
    assert exc_info.value.status_code == 401


def test_missing_allowlist_env_raises_503(monkeypatch):
    monkeypatch.delenv("SYNC_ALLOWED_SERVICE_ACCOUNTS", raising=False)
    monkeypatch.setenv("INTERNAL_SYNC_AUDIENCE", "https://livestock-mgs.example.run.app")

    with pytest.raises(HTTPException) as exc_info:
        _run(registry_auth.require_cloud_run_service_account(_creds()))
    assert exc_info.value.status_code == 503


def test_missing_audience_env_raises_503(monkeypatch):
    monkeypatch.setenv("SYNC_ALLOWED_SERVICE_ACCOUNTS", "svc@example.iam.gserviceaccount.com")
    monkeypatch.delenv("INTERNAL_SYNC_AUDIENCE", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        _run(registry_auth.require_cloud_run_service_account(_creds()))
    assert exc_info.value.status_code == 503


def test_invalid_token_raises_401(monkeypatch):
    monkeypatch.setenv("SYNC_ALLOWED_SERVICE_ACCOUNTS", "svc@example.iam.gserviceaccount.com")
    monkeypatch.setenv("INTERNAL_SYNC_AUDIENCE", "https://livestock-mgs.example.run.app")

    def fake_verify(token, request, audience):
        raise ValueError("bad token")

    monkeypatch.setattr(registry_auth.google_id_token, "verify_oauth2_token", fake_verify)

    with pytest.raises(HTTPException) as exc_info:
        _run(registry_auth.require_cloud_run_service_account(_creds("bad")))
    assert exc_info.value.status_code == 401


def test_non_allowlisted_account_raises_403(monkeypatch):
    monkeypatch.setenv("SYNC_ALLOWED_SERVICE_ACCOUNTS", "allowed@example.iam.gserviceaccount.com")
    monkeypatch.setenv("INTERNAL_SYNC_AUDIENCE", "https://livestock-mgs.example.run.app")

    def fake_verify(token, request, audience):
        return {"email": "someone-else@example.iam.gserviceaccount.com", "email_verified": True}

    monkeypatch.setattr(registry_auth.google_id_token, "verify_oauth2_token", fake_verify)

    with pytest.raises(HTTPException) as exc_info:
        _run(registry_auth.require_cloud_run_service_account(_creds()))
    assert exc_info.value.status_code == 403


def test_unverified_email_raises_403(monkeypatch):
    monkeypatch.setenv("SYNC_ALLOWED_SERVICE_ACCOUNTS", "allowed@example.iam.gserviceaccount.com")
    monkeypatch.setenv("INTERNAL_SYNC_AUDIENCE", "https://livestock-mgs.example.run.app")

    def fake_verify(token, request, audience):
        return {"email": "allowed@example.iam.gserviceaccount.com", "email_verified": False}

    monkeypatch.setattr(registry_auth.google_id_token, "verify_oauth2_token", fake_verify)

    with pytest.raises(HTTPException) as exc_info:
        _run(registry_auth.require_cloud_run_service_account(_creds()))
    assert exc_info.value.status_code == 403


def test_allowlisted_account_returns_email(monkeypatch):
    monkeypatch.setenv("SYNC_ALLOWED_SERVICE_ACCOUNTS", "allowed@example.iam.gserviceaccount.com, other@example.com")
    monkeypatch.setenv("INTERNAL_SYNC_AUDIENCE", "https://livestock-mgs.example.run.app")

    def fake_verify(token, request, audience):
        assert audience == "https://livestock-mgs.example.run.app"
        return {"email": "allowed@example.iam.gserviceaccount.com", "email_verified": True}

    monkeypatch.setattr(registry_auth.google_id_token, "verify_oauth2_token", fake_verify)

    email = _run(registry_auth.require_cloud_run_service_account(_creds()))
    assert email == "allowed@example.iam.gserviceaccount.com"
