"""Real loopback HTTP observations, not real MinerU deployment acceptance."""

import asyncio
import json

import pytest

from mineru_win7.config import MinerUConfig
from mineru_win7.errors import ServiceClosed
from mineru_win7.http import (JsonHttpClient, RequestCancelled, RequestTimeout,
                             ResponseError, TransportError)
from mineru_win7.providers.legacy_tasks import LegacyTasksProvider


def response(body, headers=b"", status=b"200 OK"):
    return (b"HTTP/1.1 " + status + b"\r\nContent-Type: application/json\r\n" + headers +
            b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body)


@pytest.mark.parametrize("payload,kind", [
    ({"gateway": "ok", "libreoffice": False, "mineru": {"status": "down"}}, "office-gateway"),
    ({"version": "3.4.2", "api_protocol_version": 2}, "native-router"),
    ({"unexpected": "format"}, "unknown"),
])
async def test_health_preserves_readiness_and_public_proxy_path(http_server, payload, kind):
    start, requests = http_server
    base = await start(response(json.dumps(payload).encode("utf-8")))
    provider = LegacyTasksProvider(MinerUConfig.from_mapping({"baseURL": base}, {}))
    try:
        value = await provider.health()
        assert value["healthFormat"] == kind and value["data"] == payload
        assert value["ok"] is True  # receipt, not component readiness
        assert requests[0].startswith(b"GET /mineru/health HTTP/1.1\r\n")
        assert b"Authorization:" not in requests[0]
    finally:
        provider.close()


@pytest.mark.parametrize("wire,error", [
    (response(b"{}", status=b"302 Found", headers=b"Location: http://unused.invalid/\r\n"), TransportError),
    (response(b"private server diagnostics", status=b"503 Unavailable"), TransportError),
    (response(b"not json"), ResponseError),
    (response(b"[]"), ResponseError),
    (response(b'{"bad": NaN}'), ResponseError),
    (response(b'{"bad": 1e999}'), ResponseError),
    (response(b"{}", headers=b"Content-Encoding: gzip\r\n"), ResponseError),
    (response(b"x" * 1025), ResponseError),
    (response(b"{}")[:-1], ResponseError),
    (b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n{}", ResponseError),
    (b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nX: " + b"x" * 17000 + b"\r\n\r\n{}", ResponseError),
    (response(b"{}", headers=b"Transfer-Encoding: chunked\r\n"), ResponseError),
    (b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\n\r\n1000000\r\n", ResponseError),
    (b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n" + b"x" * 1025, ResponseError),
])
async def test_rejects_bad_responses_without_leaking_body_or_following_redirect(http_server, wire, error):
    start, requests = http_server
    base = await start(wire)
    client = JsonHttpClient(1, 1024)
    with pytest.raises(error) as caught:
        await client.get(base + "health")
    assert "private server diagnostics" not in str(caught.value)
    assert len(requests) == 1 and not client._requests
    client.close()


@pytest.mark.parametrize("body", [
    b"Content-Length: 2\r\n\r\n{}",
    b"Transfer-Encoding: chunked\r\n\r\n1\r\n{\r\n1\r\n}\r\n0\r\nX-Trailer: ok\r\n\r\n",
    b"\r\n{}",
])
async def test_supported_bounded_body_framing(http_server, body):
    start, _ = http_server
    base = await start(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n" + body)
    client = JsonHttpClient(1, 1024)
    assert await client.get(base + "health") == {}
    client.close()


@pytest.mark.parametrize("action", ["timeout", "signal", "cancel", "unload"])
async def test_stalled_requests_release_resources(http_server, action):
    start, _ = http_server
    connected = asyncio.Event()
    base = await start(b"", connected)
    client = JsonHttpClient(0.1 if action == "timeout" else 5, 1024)
    signal = asyncio.Event()
    task = asyncio.create_task(client.get(base + "health", signal))
    await asyncio.wait_for(connected.wait(), 2)
    if action == "signal":
        signal.set()
    elif action == "cancel":
        task.cancel()
    elif action == "unload":
        client.close()
    expected = {"timeout": RequestTimeout, "signal": RequestCancelled,
                "cancel": asyncio.CancelledError, "unload": ServiceClosed}[action]
    with pytest.raises(expected):
        await asyncio.wait_for(task, 2)
    assert not client._requests
    client.close()
    with pytest.raises(ServiceClosed):
        await client.get(base + "health")


async def test_already_cancelled_request_never_connects(http_server):
    start, requests = http_server
    base = await start(response(b"{}"))
    signal = asyncio.Event()
    signal.set()
    client = JsonHttpClient(1, 1024)
    with pytest.raises(RequestCancelled):
        await client.get(base + "health", signal)
    assert requests == [] and not client._requests
    client.close()
