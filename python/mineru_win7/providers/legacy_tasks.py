"""Independently authored legacy Tasks v2 / Office Gateway adapter."""
import asyncio
import uuid

from ..errors import MinerUError, ServiceClosed
from ..http import ResponseError, TransportError
from ..transport import StreamingHttpClient


STATES = ("pending", "processing", "completed", "failed")


def task_payload(payload, expected=None):
    task = payload.get("task_id")
    if not isinstance(task, str) or not task or len(task) > 512:
        raise ResponseError("Task response has no valid task_id.")
    if expected is not None and task != expected:
        raise ResponseError("Task response identity does not match the requested task.")
    if payload.get("status") not in STATES:
        raise ResponseError("Task response has an unknown status.")
    return payload


class LegacyTasksProvider:
    def __init__(self, config, credential=None):
        self.config, self.closed = config, False
        self.http = StreamingHttpClient(config, credential)

    def endpoint(self, operation, task=None):
        if self.closed:
            raise ServiceClosed("MinerU provider has been unloaded.")
        return self.config.endpoint(operation, task)

    async def health(self, signal=None):
        payload = await self.http.get(self.endpoint("health"), signal)
        if all(key in payload for key in ("gateway", "libreoffice", "mineru")):
            kind = "office-gateway"
        elif "version" in payload and ("protocol_version" in payload or "api_protocol_version" in payload):
            kind = "native-router"
        else:
            kind = "unknown"
        return dict(ok=True, code="HEALTH_RESPONSE", message="Received health response; inspect data for readiness.",
                    healthFormat=kind, data=payload)

    async def submit(self, snapshot, options, signal=None):
        url = self.endpoint("submit")
        boundary = "mineru-" + uuid.uuid4().hex
        fields = {"return_md": "true", "return_images": "true", "response_format_zip": "true"}
        fields.update(options)
        prefix = b""
        for key, value in fields.items():
            prefix += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" %
                       (boundary, key, value)).encode("utf-8")
        filename = snapshot.name.replace('"', "_").replace("\\", "_")
        prefix += ("--%s\r\nContent-Disposition: form-data; name=\"files\"; filename=\"%s\"\r\n"
                   "Content-Type: application/octet-stream\r\n\r\n" % (boundary, filename)).encode("utf-8")
        suffix = ("\r\n--%s--\r\n" % boundary).encode("ascii")

        async def chunks():
            yield prefix
            snapshot.stream.seek(0)
            while True:
                block = snapshot.stream.read(65536)
                if not block:
                    break
                yield block
                await asyncio.sleep(0)
            yield suffix

        response = await self.http.request(url, "POST", signal,
            headers={"Content-Type": "multipart/form-data; boundary=" + boundary,
                     "Content-Length": str(len(prefix) + snapshot.size + len(suffix))},
            upload=chunks(), accepted=(202,))
        try:
            return task_payload(response.json(self.config.max_response_bytes))
        finally:
            response.close()

    async def status(self, task_id, signal=None):
        try:
            payload = await self.http.get(self.endpoint("status", task_id), signal)
            return task_payload(payload, task_id)
        except TransportError as error:
            if getattr(error, "status", None) == 404:
                missing = MinerUError("Remote task is missing or has expired.")
                missing.code = "TASK_NOT_FOUND"
                raise missing from None
            raise

    async def result(self, task_id, signal=None):
        return await self.http.request(self.endpoint("result", task_id), signal=signal,
                                       accepted=(200, 202, 409, 404), max_bytes=self.config.max_download_bytes)

    def close(self):
        self.closed = True
        self.http.close()
