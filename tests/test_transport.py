import asyncio
import ssl
from pathlib import Path

import pytest
from mineru_win7.config import MinerUConfig, LIMITS
from mineru_win7.transport import StreamingHttpClient
from mineru_win7.http import TransportError, RequestTimeout, ResponseError


@pytest.mark.parametrize("key", list(LIMITS))
def test_config_limits_are_typed_finite_and_bounded(key):
    field, default, low, high = LIMITS[key]
    assert getattr(MinerUConfig.from_mapping({key: low}, {}), field) == low
    for invalid in (True, low - 1, high + 1, float("nan"), "100"):
        with pytest.raises(ValueError, match=key):
            MinerUConfig.from_mapping({key: invalid}, {})


@pytest.mark.parametrize("trusted", [False, True])
async def test_tls_rejects_untrusted_certificate_and_accepts_explicit_private_ca(trusted):
    from conftest import HOST_ROOT
    cert = HOST_ROOT / "tests/fixtures/tls/proxy-test-cert.pem"
    key = HOST_ROOT / "tests/fixtures/tls/proxy-test-key.pem"
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert), str(key))
    handlers = set()
    async def handle(reader, writer):
        task = asyncio.current_task()
        handlers.add(task)
        try:
            await reader.readuntil(b"\r\n\r\n")
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n{}")
            await writer.drain()
        finally:
            writer.close()
            handlers.discard(task)
    server = await asyncio.start_server(handle, "127.0.0.1", 0, ssl=context)
    base = "https://127.0.0.1:%d/mineru/" % server.sockets[0].getsockname()[1]
    config = MinerUConfig.from_mapping(dict(baseURL=base, caFile=str(cert) if trusted else ""), {})
    client = StreamingHttpClient(config)
    try:
        if trusted:
            assert await client.get(base + "health") == {}
        else:
            with pytest.raises(TransportError):
                await client.get(base + "health")
        assert not client._requests
    finally:
        client.close()
        server.close()
        await server.wait_closed()
        await asyncio.gather(*list(handlers), return_exceptions=True)


async def test_rotating_credentials_only_go_to_configured_public_origin(http_server):
    start, requests = http_server
    base = await start(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n{}")
    secret = {"value": "test-token-one"}
    client = StreamingHttpClient(MinerUConfig.from_mapping(dict(baseURL=base), {}), lambda: secret["value"])
    try:
        assert await client.get(base + "health") == {}
        secret["value"] = "test-token-two"
        assert await client.get(base + "health") == {}
        assert b"Authorization: Bearer test-token-one\r\n" in requests[0]
        assert b"Authorization: Bearer test-token-two\r\n" in requests[1]
    finally:
        client.close()


async def test_idle_read_deadline_closes_socket(http_server):
    start, _ = http_server
    base = await start(b"HTTP/1.1 200 OK\r\n", asyncio.Event())
    config = MinerUConfig(base_url=base, read_timeout_seconds=0.05)
    client = StreamingHttpClient(config)
    with pytest.raises(RequestTimeout):
        await client.get(base + "health")
    assert not client._requests
    client.close()
