"""Owner isolation, authorized snapshots, durable tasks and bounded artifacts."""
import asyncio
import hashlib
import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

from .artifacts import ArtifactBuilder
from .errors import MinerUError, ServiceClosed
from .files import snapshot_file
from .http import RequestCancelled, RequestTimeout, ResponseError
from .storage import TaskStore, StorageError
from .transport import check_cancel


def fail(code, message):
    error = MinerUError(message)
    error.code = code
    return error


def success(code, **data):
    return dict(ok=True, code=code, message=code.replace("_", " ").lower(), **data)


async def publish_directory(source, destination, signal):
    # Windows indexers/virus scanners may briefly hold a newly written file.
    # Retry only the local atomic rename, never the remote submission/download.
    for attempt in range(6):
        check_cancel(signal)
        try:
            os.rename(source, destination)
            return
        except PermissionError as error:
            if getattr(error, "winerror", None) not in (5, 32) or attempt == 5:
                raise
            await asyncio.sleep(min(0.05 * (2 ** attempt), 0.25))


class MinerUService:
    def __init__(self, provider, ctx=None):
        self.provider, self.ctx = provider, ctx
        self.config = provider.config
        root = self.config.storage_directory or os.path.join(
            os.environ.get("DSH_HOME", os.path.expanduser("~/.dsh")), "data", "mineru-win7")
        self.store = TaskStore(root, self.config.base_url + "\0" + self.config.credential_ref, self.config)
        self.closed, self.active = False, set()
        self.submitting = set()
        self._mutations = asyncio.Lock()

    def owner(self, execution):
        agent = getattr(execution, "agent", None)
        agents = self.ctx.get("agents") if self.ctx is not None else None
        if agent is None or agents is None or agents.get(agent.id) is not agent:
            raise fail("OWNER_REQUIRED", "A live registered host Agent is required.")
        session = getattr(agent, "session", None)
        if session is None or getattr(execution, "session", session) is not session:
            raise fail("OWNER_REQUIRED", "Execution session must match its live Agent.")
        return hashlib.sha256((str(session.id) + "\0" + str(agent.id)).encode("utf-8")).hexdigest()

    async def health(self, signal=None):
        return await self.provider.health(signal)

    async def execute(self, operation, arguments, execution):
        if self.closed:
            raise ServiceClosed("MinerU plugin has been unloaded.")
        check_cancel(execution.signal)
        task = asyncio.current_task()
        self.active.add(task)
        try:
            if operation == "health":
                return await self.health(execution.signal)
            owner = self.owner(execution)
            method = getattr(self, "_" + operation)
            return await method(arguments, execution, owner)
        finally:
            self.active.discard(task)

    def public(self, record):
        keys = ("task_id", "status", "source_name", "source_sha256", "created_at", "updated_at",
                "remote_file_names", "artifacts", "result_mapping", "submission_error")
        value = {key: record[key] for key in keys if key in record}
        if record.get("artifacts") is not None:
            value["artifact_count"] = len(record["artifacts"])
            value["artifacts"] = record["artifacts"][:100]
            value["manifest_truncated"] = len(record["artifacts"]) > 100
            value["directory"] = str(self.store.directory(record["task_id"]))
        if record.get("status") == "submitting" and not record.get("remote_id"):
            value["status"] = "submission-unknown"
        return value

    def options(self, args, name):
        ext = Path(name).suffix.lower()
        allowed = (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".gif",
                   ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx")
        if ext not in allowed:
            raise fail("INVALID_ARGUMENT", "Unsupported document or image extension.")
        mode = args.get("office_mode", self.config.office_mode)
        if mode not in ("native", "pdf_ocr") or (mode == "native" and ext in (".doc", ".ppt", ".xls")):
            raise fail("INVALID_ARGUMENT", "Legacy Office files require pdf_ocr mode.")
        fields = {"office_mode": mode}
        for key, allowed_values in (("parse_method", ("auto", "txt", "ocr")),
                                    ("backend", ("pipeline", "vlm-engine", "hybrid-auto-engine"))):
            if key in args:
                if args[key] not in allowed_values:
                    raise fail("INVALID_ARGUMENT", "Unsupported " + key)
                fields[key] = args[key]
        if "language" in args:
            language = args["language"]
            if not isinstance(language, str) or not language or len(language) > 32 or not all(c.isalnum() or c in "_-" for c in language):
                raise fail("INVALID_ARGUMENT", "Invalid OCR language.")
            fields["lang_list"] = language
        fields["response_format_zip"] = "true" if args.get("format", "zip") == "zip" else "false"
        if args.get("format", "zip") not in ("zip", "json"):
            raise fail("INVALID_ARGUMENT", "format must be zip or json.")
        fields["return_images"] = "true" if args.get("images", True) else "false"
        return fields

    async def _submit(self, args, execution, owner):
        self.provider.endpoint("submit")
        fields = self.options(args, args["file_path"])
        # Snapshot stays disk-backed; all source access uses ctx.fs.
        snapshot = await snapshot_file(self.ctx, execution, args["file_path"], self.config.max_upload_bytes)
        try:
            async with self._mutations:
                if self.store.reserve() < snapshot.size:
                    raise StorageError("Storage quota has no room for this upload.")
                now = time.time()
                record = dict(task_id=uuid.uuid4().hex, owner=owner, status="submitting", created_at=now,
                              updated_at=now, source_name=snapshot.name, source_sha256=snapshot.sha256,
                              source_size=snapshot.size)
                self.store.put(record)
                self.submitting.add(record["task_id"])
            try:
                remote = await self.provider.submit(snapshot, fields, execution.signal)
                self.config.endpoint("status", remote["task_id"])
                record.update(remote_id=remote["task_id"], status=remote["status"],
                              remote_file_names=self.file_names(remote), updated_at=time.time())
                self.store.put(record)
            except BaseException as error:
                # A lost POST response does not prove the server rejected the task.
                record.update(status="submission-unknown", updated_at=time.time(),
                              submission_error="Submission outcome unknown; do not retry automatically.")
                self.store.put(record)
                if isinstance(error, MinerUError):
                    error.task_id = record["task_id"]
                raise
            finally:
                self.submitting.discard(record["task_id"])
            return success("TASK_SUBMITTED", task=self.public(record))
        finally:
            snapshot.close()

    def file_names(self, remote):
        names = remote.get("file_names", [])
        if not isinstance(names, list) or len(names) > self.config.max_files or any(not isinstance(name, str) or len(name) > 512 for name in names):
            raise ResponseError("Invalid remote file_names.")
        return names

    async def _list(self, args, execution, owner):
        offset, limit = self.page(args)
        records = self.store.list(owner)
        tasks = []
        for record in records[offset:offset + limit]:
            item = self.public(record)
            item.pop("artifacts", None)
            item.pop("result_mapping", None)
            tasks.append(item)
        return success("TASKS", tasks=tasks, next_offset=offset + len(tasks), eof=offset + len(tasks) >= len(records))

    def page(self, args):
        offset, limit = args.get("offset", 0), args.get("limit", 20)
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise fail("INVALID_ARGUMENT", "Invalid pagination offset or limit (maximum 100).")
        return offset, limit

    async def _files(self, args, execution, owner):
        record = self.store.get(args["task_id"], owner)
        offset, limit = self.page(args)
        artifacts = record.get("artifacts", [])
        return success("ARTIFACTS", files=artifacts[offset:offset + limit],
                       next_offset=min(len(artifacts), offset + limit), eof=offset + limit >= len(artifacts))

    def remote_task(self, args, owner):
        record = self.store.get(args["task_id"], owner)
        if not record.get("remote_id"):
            raise fail("SUBMISSION_UNKNOWN", "No acknowledged remote ID; inspect this local submission before retrying.")
        return record

    async def _status(self, args, execution, owner):
        record = self.remote_task(args, owner)
        remote = await self.provider.status(record["remote_id"], execution.signal)
        record.update(status=remote["status"], remote_file_names=self.file_names(remote), updated_at=time.time())
        # Preserve artifact metadata published by a concurrent result request.
        current = self.store.get(record["task_id"], owner)
        current.update({key: record[key] for key in ("status", "remote_file_names", "updated_at")})
        self.store.put(current)
        return success("TASK_STATUS", task=self.public(current))

    async def _result(self, args, execution, owner):
        async with self._mutations:
            record = self.remote_task(args, owner)
            if record.get("artifacts") is not None:
                for artifact in record["artifacts"]:
                    self.store.verified_path(record, artifact["name"])
                return success("RESULT_CACHED", task=self.public(record))
            budget = self.store.reserve(new_task=False)
            response = await self.provider.result(record["remote_id"], execution.signal)
            try:
                if response.status != 200:
                    code = {202: "RESULT_NOT_READY", 409: "TASK_FAILED", 404: "TASK_NOT_FOUND"}[response.status]
                    return dict(ok=False, code=code, message=code.replace("_", " ").lower(), task=self.public(record))
                directory = self.store.directory(record["task_id"])
                if directory.exists():
                    raise StorageError("Unpublished result directory exists; preserving it for recovery.")
                with tempfile.TemporaryDirectory(prefix="stage-", dir=str(self.store.root)) as staging:
                    builder = ArtifactBuilder(staging, self.config, budget, execution.signal)
                    if response.media_type in (b"application/zip", b"application/x-zip-compressed", b"application/octet-stream"):
                        mapping = await builder.zip(response.body)
                    else:
                        mapping = await builder.json(response)
                    if not builder.files:
                        raise ResponseError("Result contains no artifact files.")
                    check_cancel(execution.signal)
                    await publish_directory(staging, str(directory), execution.signal)
                    record.update(status="completed", artifacts=builder.files, result_mapping=mapping,
                                  updated_at=time.time())
                    self.store.put(record)
                return success("RESULT_SAVED", task=self.public(record))
            finally:
                response.close()

    async def _read(self, args, execution, owner):
        record = self.store.get(args["task_id"], owner)
        name = args.get("artifact")
        if not name:
            name = next((item["name"] for item in record.get("artifacts", []) if item["name"].lower().endswith(".md")), None)
        if not name:
            raise fail("ARTIFACT_REQUIRED", "Choose an artifact from the saved task manifest.")
        if not name.lower().endswith((".md", ".txt", ".json")):
            raise fail("INVALID_ARGUMENT", "Only UTF-8 Markdown, text and JSON artifacts can be read.")
        offset, limit = args.get("offset", 0), args.get("limit", self.config.read_max_chars)
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= self.config.read_max_chars:
            raise fail("INVALID_ARGUMENT", "Invalid character offset or read limit.")
        path = self.store.verified_path(record, name)
        with path.open("r", encoding="utf-8", newline="") as stream:
            remaining = offset
            while remaining:
                check_cancel(execution.signal)
                block = stream.read(min(65536, remaining))
                if not block:
                    break
                remaining -= len(block)
                await asyncio.sleep(0)
            text = stream.read(limit)
            eof = not stream.read(1)
        return success("ARTIFACT_TEXT", artifact=name, text=text, offset=offset,
                       next_offset=offset + len(text), eof=eof)

    async def _forget(self, args, execution, owner):
        async with self._mutations:
            record = self.store.get(args["task_id"], owner)
            if record["task_id"] in self.submitting:
                raise fail("TASK_BUSY", "Submission is still in flight; stop or finish it before forgetting this task.")
            self.store.forget(record)
        return success("LOCAL_TASK_FORGOTTEN")

    async def _wait(self, args, execution, owner):
        record = self.remote_task(args, owner)
        if args.get("background", False):
            jobs = self.ctx.get("jobs")
            if jobs is None:
                raise fail("JOBS_UNAVAILABLE", "Background waiting requires the host jobs service and controller.")
            output, stopped = {"text": "Waiting locally; remote task is not cancelled by job_kill."}, asyncio.Event()
            background_execution = SimpleNamespace(agent=execution.agent, session=execution.agent.session, signal=stopped)
            options = dict(args, background=False)

            async def run():
                try:
                    result = await self.execute("wait", options, background_execution)
                    output["text"] = json.dumps(result, ensure_ascii=False)
                    return {"status": "completed" if result["ok"] else "failed", "output": output["text"]}
                except (RequestCancelled, asyncio.CancelledError):
                    return {"status": "killed", "output": "Local wait stopped; remote task was not cancelled."}
                except MinerUError as error:
                    output["text"] = error.code + ": " + str(error)
                    return {"status": "failed", "output": output["text"]}

            def start():
                task = asyncio.create_task(run())
                return dict(done=task, cancel=lambda reason=None: stopped.set(), readOutput=lambda: output["text"])

            try:
                job = jobs.start(dict(kind="mineru", label=record["source_name"], owner=execution.agent,
                                      outputLimitBytes=8192, run=start))
            except ValueError:
                raise fail("JOBS_UNAVAILABLE", "Host jobs controller is unavailable or its owner limit has been reached.") from None
            return success("BACKGROUND_WAIT_STARTED", job_id=job, task=self.public(record))
        timeout = args.get("timeout_seconds", self.config.wait_timeout_seconds)
        if type(timeout) is not int or not 1 <= timeout <= self.config.wait_timeout_seconds:
            raise fail("INVALID_ARGUMENT", "Invalid wait timeout.")
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            check_cancel(execution.signal)
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise RequestTimeout("Local polling deadline reached; remote task was not cancelled.")
            try:
                result = await asyncio.wait_for(self._status(args, execution, owner), remaining)
                state = result["task"]["status"]
                if state == "failed":
                    return dict(result, ok=False, code="TASK_FAILED")
                if state == "completed":
                    return await asyncio.wait_for(self._result(args, execution, owner),
                        max(0.001, deadline - asyncio.get_running_loop().time())) if args.get("download", True) else result
            except asyncio.TimeoutError:
                raise RequestTimeout("Local polling deadline reached; remote task was not cancelled.") from None
            # Short cancellable waits avoid a second controller-specific signal ABI.
            pause_until = min(deadline, asyncio.get_running_loop().time() + self.config.poll_interval_seconds)
            while asyncio.get_running_loop().time() < pause_until:
                check_cancel(execution.signal)
                await asyncio.sleep(min(0.1, max(0, pause_until - asyncio.get_running_loop().time())))

    async def close(self):
        self.closed = True
        self.provider.close()
        pending = [task for task in self.active if task is not asyncio.current_task()]
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        self.store.close()
