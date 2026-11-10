"""Streaming HTTP transport; response bodies spool to disk, never to x86 RAM."""
import asyncio
import json
import math
import ssl
import tempfile
from urllib.parse import quote, urlsplit

from .http import JsonHttpClient, ResponseError, TransportError, RequestTimeout, RequestCancelled


def check_cancel(signal):
    if signal is not None and (getattr(signal, "aborted", False) or
                               (hasattr(signal, "is_set") and signal.is_set())):
        raise RequestCancelled("Stopped locally; remote tasks are not cancelled.")


def parse_json(raw):
    def reject(value):
        raise ValueError("Non-finite JSON number")

    def finite(value):
        number = float(value)
        return number if math.isfinite(number) else reject(value)

    try:
        value = json.loads(raw.decode("utf-8"), parse_constant=reject, parse_float=finite)
        if not isinstance(value, dict):
            raise ValueError("Expected object")
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise ResponseError("MinerU response must be a finite JSON object.") from None


class HttpResponse:
    def __init__(self, status, headers, body):
        self.status, self.headers, self.body = status, headers, body

    @property
    def media_type(self):
        return self.headers.get(b"content-type", b"").split(b";", 1)[0].strip().lower()

    def json(self, limit):
        media = self.media_type
        if media != b"application/json" and not (media.startswith(b"application/") and media.endswith(b"+json")):
            raise ResponseError("MinerU response must have a JSON content type.")
        self.body.seek(0)
        raw = self.body.read(limit + 1)
        if len(raw) > limit:
            raise ResponseError("JSON response exceeds its byte budget.")
        return parse_json(raw)

    def close(self):
        self.body.close()


class StreamingHttpClient(JsonHttpClient):
    def __init__(self, config, credential=None):
        super().__init__(config.request_timeout_seconds, config.max_response_bytes)
        self.config, self.credential = config, credential
        self._slots = asyncio.Semaphore(4)

    async def request(self, url, method="GET", signal=None, headers=None, upload=None,
                      accepted=(200,), max_bytes=None):
        return await super().get(url, signal, _operation=lambda: self._exchange(
            url, method, headers or {}, upload, accepted, max_bytes or self.max_bytes))

    async def _get(self, url):
        response = await self._exchange(url, "GET", {}, None, (200,), self.max_bytes)
        try:
            return response.json(self.max_bytes)
        finally:
            response.close()

    async def _exchange(self, *args):
        async with self._slots:
            return await self._connected(*args)

    async def _connected(self, url, method, headers, upload, accepted, maximum):
        parsed = urlsplit(url)
        writer, body = None, None
        try:
            secure = parsed.scheme == "https"
            context = ssl.create_default_context(cafile=self.config.ca_file or None) if secure else None
            reader, writer = await asyncio.wait_for(asyncio.open_connection(
                parsed.hostname, parsed.port or (443 if secure else 80), ssl=context,
                limit=self.HEADER_LIMIT), self.config.connect_timeout_seconds)
            host = parsed.hostname.encode("idna").decode("ascii")
            if ":" in host:
                host = "[" + host + "]"
            if parsed.port is not None:
                host += ":" + str(parsed.port)
            path = quote(parsed.path or "/", safe="/%:@!$&'()*+,;=-._~")
            fields = {"Host": host, "Accept": "application/json, application/zip",
                      "Accept-Encoding": "identity", "Connection": "close"}
            fields.update(headers)
            if self.credential is not None:
                token = self.credential()
                if token:
                    fields["Authorization"] = "Bearer " + token
            for key, value in fields.items():
                if any(ord(c) < 32 or ord(c) == 127 for c in key + value):
                    raise ValueError("Invalid HTTP request header")
            wire = "%s %s HTTP/1.1\r\n" % (method, path)
            wire += "".join(key + ": " + value + "\r\n" for key, value in fields.items()) + "\r\n"
            writer.write(wire.encode("ascii"))
            await asyncio.wait_for(writer.drain(), self.config.read_timeout_seconds)
            if upload is not None:
                async for block in upload:
                    writer.write(block)
                    await asyncio.wait_for(writer.drain(), self.config.read_timeout_seconds)

            async def read(name, *args):
                return await asyncio.wait_for(getattr(reader, name)(*args), self.config.read_timeout_seconds)

            header = await read("readuntil", b"\r\n\r\n")
            if len(header) > self.HEADER_LIMIT:
                raise ResponseError("Response headers exceed their byte budget.")
            lines = header[:-4].split(b"\r\n")
            status = lines[0].split(b" ", 2)
            if (len(status) < 2 or status[0] not in (b"HTTP/1.0", b"HTTP/1.1") or
                    len(status[1]) != 3 or not status[1].isdigit()):
                raise ResponseError("Invalid HTTP status line.")
            status = int(status[1])
            if status not in accepted:
                error = TransportError("MinerU request returned HTTP %d." % status)
                error.status = status
                raise error
            response_headers = {}
            for line in lines[1:]:
                key, sep, value = line.partition(b":")
                key = key.lower()
                if not sep or key in response_headers:
                    raise ResponseError("Invalid or duplicate HTTP response header.")
                response_headers[key] = value.strip()
            if response_headers.get(b"content-encoding", b"identity").lower() != b"identity":
                raise ResponseError("Compressed HTTP responses are not supported.")
            length = response_headers.get(b"content-length")
            transfer = response_headers.get(b"transfer-encoding")
            body, total = tempfile.TemporaryFile(mode="w+b"), 0

            async def consume(size):
                nonlocal total
                if size > maximum - total:
                    raise ResponseError("Response exceeds its byte budget.")
                while size:
                    block = await read("readexactly", min(65536, size))
                    body.write(block)
                    size -= len(block)
                    total += len(block)

            if transfer is not None:
                if transfer.lower() != b"chunked" or length is not None:
                    raise ResponseError("Unsupported or ambiguous HTTP framing.")
                while True:
                    line = await read("readuntil", b"\r\n")
                    size_text = line[:-2].split(b";", 1)[0]
                    if not size_text or any(c not in b"0123456789abcdefABCDEF" for c in size_text):
                        raise ResponseError("Invalid HTTP chunk size.")
                    size = int(size_text, 16)
                    if size == 0:
                        used = 0
                        while True:
                            trailer = await read("readuntil", b"\r\n")
                            used += len(trailer)
                            if used > self.HEADER_LIMIT:
                                raise ResponseError("HTTP trailers exceed their byte budget.")
                            if trailer == b"\r\n":
                                break
                        break
                    await consume(size)
                    if await read("readexactly", 2) != b"\r\n":
                        raise ResponseError("Invalid chunk terminator.")
            elif length is not None:
                if not length.isdigit() or len(length) > 10:
                    raise ResponseError("Invalid Content-Length.")
                await consume(int(length))
            else:
                while True:
                    block = await read("read", min(65536, maximum + 1 - total))
                    if not block:
                        break
                    total += len(block)
                    if total > maximum:
                        raise ResponseError("Response exceeds its byte budget.")
                    body.write(block)
            body.seek(0)
            result = HttpResponse(status, response_headers, body)
            body = None
            return result
        except asyncio.TimeoutError:
            raise RequestTimeout("MinerU connection or I/O exceeded its deadline.") from None
        except OSError:
            raise TransportError("Unable to communicate with MinerU or validate its TLS certificate.") from None
        except (ValueError, UnicodeError, RecursionError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            raise ResponseError("Malformed, truncated or oversized MinerU response.") from None
        finally:
            if body is not None:
                body.close()
            if writer is not None:
                writer.close()
                writer.transport.abort()
