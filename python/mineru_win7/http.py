"""Small HTTP/1.1 GET transport with bounded memory and cancellable sockets.

No redirects, proxies, retries or decompression. TLS uses system trust validation.
The total deadline covers DNS, connect, TLS, headers and body.
"""

import asyncio
from typing import Any, Dict, Set

from .errors import MinerUError, ServiceClosed


class TransportError(MinerUError):
    code = "HTTP_ERROR"


class ResponseError(MinerUError):
    code = "INVALID_RESPONSE"


class RequestTimeout(MinerUError):
    code = "REQUEST_TIMEOUT"


class RequestCancelled(MinerUError):
    code = "REQUEST_CANCELLED"


class JsonHttpClient:
    HEADER_LIMIT = 16384

    def __init__(self, timeout: float, max_bytes: int):
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.closed = False
        self._requests = set()  # type: Set[asyncio.Task]

    async def get(self, url: str, signal=None, _operation=None) -> Dict[str, Any]:
        if self.closed:
            raise ServiceClosed("MinerU HTTP client has been unloaded.")
        if signal is not None and (getattr(signal, "aborted", False) or
                                   (hasattr(signal, "is_set") and signal.is_set())):
            raise RequestCancelled("MinerU request was cancelled locally.")
        operation = self._get(url) if _operation is None else _operation()
        request = asyncio.create_task(operation)
        self._requests.add(request)
        watcher = None
        delivered = False
        try:
            if signal is not None:
                wait = getattr(signal, "wait_aborted", None) or getattr(signal, "wait", None)
                if wait is not None:
                    watcher = asyncio.create_task(wait())
            tasks = {request} if watcher is None else {request, watcher}
            done, _ = await asyncio.wait(tasks, timeout=self.timeout,
                                         return_when=asyncio.FIRST_COMPLETED)
            if not done:
                raise RequestTimeout("MinerU request exceeded its total deadline.")
            if watcher is not None and watcher in done:
                raise RequestCancelled("MinerU request was cancelled locally.")
            result = await request
            delivered = True
            return result
        except asyncio.CancelledError:
            if self.closed:
                raise ServiceClosed("MinerU HTTP client has been unloaded.")
            raise
        finally:
            request.cancel()
            if watcher is not None:
                watcher.cancel()
            await asyncio.gather(*([request] if watcher is None else [request, watcher]),
                                 return_exceptions=True)
            if not delivered and not request.cancelled() and request.exception() is None:
                value = request.result()
                if hasattr(value, "close"):
                    value.close()
            self._requests.discard(request)

    async def _get(self, url: str) -> Dict[str, Any]:
        # Lazy imports keep the cancellation runner independent of wire framing.
        from .config import MinerUConfig
        from .transport import StreamingHttpClient
        config = MinerUConfig(request_timeout_seconds=self.timeout,
                              max_response_bytes=self.max_bytes)
        return await StreamingHttpClient(config)._get(url)

    def close(self) -> None:
        self.closed = True
        for task in list(self._requests):
            task.cancel()
