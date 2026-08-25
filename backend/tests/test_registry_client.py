"""Unit tests for registry_client.py — the Registry service is fully mocked (no network)."""
import asyncio
import time

import httpx
import pytest

import registry_client
from registry_client import RegistryClient, RegistryConflict, RegistryNotFound, RegistryUnavailable


def _run(coro):
    return asyncio.run(coro)


def _client():
    return RegistryClient(base_url="https://registry.example.com", audience="https://registry.example.com")


def _response(status_code, method="GET", path="/tags", json=None):
    return httpx.Response(
        status_code,
        json=json,
        request=httpx.Request(method, f"https://registry.example.com{path}"),
    )


class _StubTokenCache:
    def get(self):
        return "fake-token"


@pytest.fixture(autouse=True)
def _stub_token_cache(monkeypatch):
    monkeypatch.setattr(registry_client, "_get_token_cache", lambda audience: _StubTokenCache())


def _fake_async_client(*, response=None, exc=None, capture=None):
    class _Fake:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def request(self, method, path, headers=None, **kwargs):
            if capture is not None:
                capture["method"] = method
                capture["path"] = path
                capture["headers"] = headers
                capture["kwargs"] = kwargs
            if exc is not None:
                raise exc
            return response

    def factory(*args, **kwargs):
        return _Fake()

    return factory


def test_search_tags_success_returns_json(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _fake_async_client(response=_response(200, json={"items": []})))

    result = _run(_client().search_tags("Jane"))

    assert result == {"items": []}


def test_post_status_409_raises_conflict_with_current_status(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        _fake_async_client(
            response=_response(409, method="POST", path="/tags/T1/status", json={"current_status": "SOLD"})
        ),
    )

    with pytest.raises(RegistryConflict) as exc_info:
        _run(_client().post_status("Jane", "T1", status="ACTIVE", source_event_id="evt-1"))

    assert exc_info.value.current_status == "SOLD"


def test_post_event_404_raises_not_found(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        _fake_async_client(response=_response(404, method="POST", path="/tags/T1/events")),
    )

    with pytest.raises(RegistryNotFound):
        _run(_client().post_event("Jane", "T1", event_type="CALVED", source_event_id="evt-1", payload={}))


def test_revert_5xx_raises_unavailable(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        _fake_async_client(response=_response(503, method="POST", path="/tags/T1/revert")),
    )

    with pytest.raises(RegistryUnavailable):
        _run(_client().revert("Jane", "T1", source_event_id="evt-1", previous_status="ACTIVE"))


def test_timeout_raises_unavailable(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _fake_async_client(exc=httpx.ConnectTimeout("timed out")))

    with pytest.raises(RegistryUnavailable):
        _run(_client().search_tags("Jane"))


def test_connect_error_raises_unavailable(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _fake_async_client(exc=httpx.ConnectError("refused")))

    with pytest.raises(RegistryUnavailable):
        _run(_client().search_tags("Jane"))


def test_post_event_sends_actor_header_and_payload(monkeypatch):
    capture = {}
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        _fake_async_client(response=_response(200, method="POST", path="/tags/T1/events", json={"ok": True}), capture=capture),
    )

    result = _run(_client().post_event("Jane Doe", "T1", event_type="CALVED", source_event_id="evt-1", payload={"count": 2}))

    assert result == {"ok": True}
    assert capture["method"] == "POST"
    assert capture["path"] == "/tags/T1/events"
    assert capture["headers"]["X-Actor-Name"] == "Jane Doe"
    assert capture["headers"]["Authorization"] == "Bearer fake-token"
    assert capture["kwargs"]["json"] == {"event_type": "CALVED", "source_event_id": "evt-1", "payload": {"count": 2}}


def test_id_token_cache_refetches_after_expiry(monkeypatch):
    calls = {"n": 0}

    def fake_fetch(request, audience):
        calls["n"] += 1
        return f"token-{calls['n']}"

    def fake_claims(token):
        if token == "token-1":
            return {"exp": time.time() - 10}
        return {"exp": time.time() + 3600}

    monkeypatch.setattr(registry_client.google_id_token, "fetch_id_token", fake_fetch)
    monkeypatch.setattr(registry_client.jose_jwt, "get_unverified_claims", fake_claims)

    cache = registry_client._IdTokenCache("aud")
    first = cache.get()
    second = cache.get()

    assert first == "token-1"
    assert second == "token-2"
    assert calls["n"] == 2


def test_id_token_cache_reuses_valid_token(monkeypatch):
    calls = {"n": 0}

    def fake_fetch(request, audience):
        calls["n"] += 1
        return "token-1"

    def fake_claims(token):
        return {"exp": time.time() + 3600}

    monkeypatch.setattr(registry_client.google_id_token, "fetch_id_token", fake_fetch)
    monkeypatch.setattr(registry_client.jose_jwt, "get_unverified_claims", fake_claims)

    cache = registry_client._IdTokenCache("aud")
    cache.get()
    cache.get()

    assert calls["n"] == 1
