"""Loopback-only legacy Tasks fixture. It never performs OCR or calls a model."""
import argparse
import asyncio
import base64
import io
import json
from pathlib import Path
import re
import time
import zipfile


TEXT = "# 本地协议验证\n\n这是模拟结果，不是 OCR 输出。\n<script>window.mineruUnsafe = true</script>\n" + "分页内容。\n" * 4000
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=")


class OfflineMinerU:
    def __init__(self):
        self.tasks, self.requests, self.handlers = {}, [], set()
        self.server = None

    async def start(self, port=0):
        self.server = await asyncio.start_server(self.handle, "127.0.0.1", port)
        self.base_url = "http://127.0.0.1:%d/mineru/" % self.server.sockets[0].getsockname()[1]
        return self

    async def close(self):
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
        pending = list(self.handlers)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    def status(self, task):
        age = time.monotonic() - task["created"]
        if task["name"].startswith("failed"):
            return "failed"
        if task["name"].startswith("slow"):
            return "processing"
        return "completed" if age >= 0.5 else "processing"

    def payload(self, identifier):
        task = self.tasks[identifier]
        return dict(task_id=identifier, status=self.status(task), file_names=["converted.pdf"],
                    status_url="http://container.invalid/private", result_url="http://container.invalid/private/result")

    async def handle(self, reader, writer):
        current = asyncio.current_task()
        self.handlers.add(current)
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
            first, *lines = head.split(b"\r\n")
            method, path, _ = first.decode("ascii").split(" ")
            headers = dict(line.split(b":", 1) for line in lines if b":" in line)
            headers = {key.lower(): value.strip() for key, value in headers.items()}
            size = int(headers.get(b"content-length", b"0"))
            if size < 0 or size > 104857600:
                raise ValueError("fixture request budget")
            prefix, remaining = b"", size
            while remaining:
                block = await asyncio.wait_for(reader.readexactly(min(65536, remaining)), 10)
                prefix = (prefix + block)[:65536]
                remaining -= len(block)
            if len(self.requests) >= 10000:
                raise ValueError("fixture event budget")
            self.requests.append(dict(method=method, path=path, bytes=size))
            code, media, body = 200, "application/json", None
            if method == "GET" and path == "/mineru/health":
                body = dict(gateway="LOCAL PROTOCOL FIXTURE ONLY", libreoffice=True, mineru=True)
            elif method == "POST" and path == "/mineru/tasks":
                match = re.search(br'name="files"; filename="([^"]+)"', prefix)
                if match is None or not headers.get(b"content-type", b"").startswith(b"multipart/form-data;"):
                    code, body = 400, dict(error="single multipart files field required")
                else:
                    name = match.group(1).decode("utf-8")
                    identifier = "fixture-%04d" % (len(self.tasks) + 1)
                    self.tasks[identifier] = dict(name=name, created=time.monotonic(),
                        zipped=b'name="response_format_zip"\r\n\r\ntrue' in prefix)
                    if name.startswith("disconnect"):
                        return  # Deliberately lose the acknowledgement, without retrying.
                    code, body = 202, self.payload(identifier)
            else:
                match = re.fullmatch(r"/mineru/tasks/(fixture-\d+)(/result)?", path)
                if method != "GET" or match is None or match.group(1) not in self.tasks:
                    code, body = 404, dict(error="fixture task missing")
                else:
                    identifier = match.group(1)
                    task = self.tasks[identifier]
                    body = self.payload(identifier)
                    if match.group(2):
                        state = body["status"]
                        if state != "completed":
                            code = 409 if state == "failed" else 202
                        elif task["zipped"]:
                            stream = io.BytesIO()
                            with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
                                archive.writestr("converted/ocr/converted.md", TEXT)
                                archive.writestr("converted/ocr/images/probe.png", PNG)
                            body, media = stream.getvalue(), "application/zip"
                        else:
                            body = dict(results={"converted-pdf": dict(md_content=TEXT,
                                images={"probe.png": "data:image/png;base64," + base64.b64encode(PNG).decode("ascii")})})
            raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
            writer.write(("HTTP/1.1 %d Fixture\r\nContent-Type: %s\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" %
                          (code, media, len(raw))).encode("ascii") + raw)
            await writer.drain()
        except (ConnectionError, asyncio.TimeoutError, asyncio.IncompleteReadError, ValueError):
            pass
        finally:
            writer.close()
            self.handlers.discard(current)


async def serve(args):
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    fixture = await OfflineMinerU().start(args.port)
    (output / "ready.json").write_text(json.dumps(dict(baseURL=fixture.base_url, kind="LOCAL FIXTURE; NO OCR")), encoding="utf-8")
    print(fixture.base_url, flush=True)
    try:
        while not (output / "stop").exists():
            await asyncio.sleep(0.1)
    finally:
        await fixture.close()
        (output / "requests.json").write_text(json.dumps(fixture.requests, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="Fresh owned directory; create stop file to exit")
    parser.add_argument("--port", type=int, default=0)
    asyncio.run(serve(parser.parse_args()))
