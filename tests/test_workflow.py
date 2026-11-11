import asyncio
import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from dsh.core.tools import ToolExecutionInput


async def call(ctx, owner, operation, **arguments):
    result = await ctx.get("tools").execute(ToolExecutionInput("test", "mineru_" + operation,
        arguments, agent=owner, signal=asyncio.Event()))
    assert not result.is_error, result.error
    return result.value


async def submit(ctx, a, tmp_path, **options):
    path = tmp_path / "中文.docx"
    path.write_bytes(b"office-content")
    result = await call(ctx, a, "submit", file_path=str(path), **options)
    assert result["ok"], result
    return result["task"]["task_id"]


async def test_owner_bound_full_json_journey_and_cold_cache(plugin_context, task_server, tmp_path):
    ctx, a, b, fiber = await plugin_context()
    identifier = await submit(ctx, a, tmp_path, format="json")
    assert identifier != "remote-1"
    method, path, headers, body = task_server["requests"][0]
    assert method == "POST" and path == "/mineru/tasks"
    assert int(headers[b"Content-Length"]) == len(body)
    assert b'name="files"' in body and b"office-content" in body and b"pdf_ocr" in body
    assert '中文.docx'.encode("utf-8") in body
    before = len(task_server["requests"])
    for operation in ("status", "result", "read", "forget", "wait"):
        denied = await call(ctx, b, operation, task_id=identifier)
        assert not denied["ok"] and denied["code"] == "TASK_NOT_FOUND"
    assert len(task_server["requests"]) == before
    assert (await call(ctx, b, "list"))["tasks"] == []
    task_server["status"] = "completed"
    assert (await call(ctx, a, "status", task_id=identifier))["task"]["remote_file_names"] == ["converted.pdf"]
    result = await call(ctx, a, "result", task_id=identifier)
    assert result["code"] == "RESULT_SAVED"
    assert result["task"]["source_name"] == "中文.docx"
    assert result["task"]["result_mapping"][0]["remote_name"] == "converted-pdf"
    text = await call(ctx, a, "read", task_id=identifier, limit=4)
    assert text["text"] == "# 中文" and text["next_offset"] == 4 and not text["eof"]
    assert (await call(ctx, a, "read", task_id=identifier, offset=4))["text"].startswith("\nHello")
    assert all(row[1].startswith("/mineru/tasks") for row in task_server["requests"])
    await fiber.dispose()
    await fiber.await_settled()
    ctx2, a2, _, _ = await plugin_context()
    before = len(task_server["requests"])
    assert (await call(ctx2, a2, "result", task_id=identifier))["code"] == "RESULT_CACHED"
    assert len(task_server["requests"]) == before
    assert (await call(ctx2, a2, "forget", task_id=identifier))["ok"]
    assert (await call(ctx2, a2, "list"))["tasks"] == []


@pytest.mark.parametrize("status,code", [(202, "RESULT_NOT_READY"), (409, "TASK_FAILED"), (404, "TASK_NOT_FOUND")])
async def test_result_http_states(plugin_context, task_server, tmp_path, status, code):
    ctx, a, _, _ = await plugin_context()
    identifier = await submit(ctx, a, tmp_path)
    task_server["result_status"] = status
    result = await call(ctx, a, "result", task_id=identifier)
    assert result["code"] == code and not result["ok"]


async def test_missing_status_and_unknown_submission_not_retried(plugin_context, task_server, tmp_path):
    ctx, a, _, _ = await plugin_context()
    task_server["drop_submit"] = True
    path = tmp_path / "one.pdf"
    path.write_bytes(b"%PDF")
    result = await call(ctx, a, "submit", file_path=str(path))
    assert not result["ok"] and result["task_id"]
    tasks = (await call(ctx, a, "list"))["tasks"]
    assert len(tasks) == 1 and tasks[0]["status"] == "submission-unknown"
    assert len(task_server["requests"]) == 1
    assert (await call(ctx, a, "status", task_id=result["task_id"]))["code"] == "SUBMISSION_UNKNOWN"


def zipped(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries:
            info = zipfile.ZipInfo(name)
            # ZipInfo normally normalizes native separators on Windows. Preserve
            # hostile raw wire names so this fixture tests the actual boundary.
            info.filename = name
            archive.writestr(info, content)
    return stream.getvalue()


async def test_zip_result_cache_tampering_and_conservative_forget(plugin_context, task_server, tmp_path):
    ctx, a, _, _ = await plugin_context()
    identifier = await submit(ctx, a, tmp_path)
    task_server.update(result_type="application/zip", result_body=zipped([("converted/ocr/converted.md", "# OK\n"),
                                                                       ("converted/ocr/images/1.png", b"image")]))
    result = await call(ctx, a, "result", task_id=identifier)
    assert result["ok"], result
    root = Path(result["task"]["directory"])
    (root / "unknown.txt").write_text("preserve", encoding="utf-8")
    assert not (await call(ctx, a, "forget", task_id=identifier))["ok"]
    assert (root / "unknown.txt").exists()
    (root / "converted/ocr/converted.md").write_text("tampered", encoding="utf-8")
    assert (await call(ctx, a, "read", task_id=identifier))["code"] == "STORAGE_ERROR"


@pytest.mark.parametrize("name", ["../escape.md", "/absolute.md", "C:/escape.md", "CON.txt", "dir/../x.md", "dir\\evil.md", "x:ads", "tail. "])
async def test_unsafe_zip_never_publishes_artifacts(plugin_context, task_server, tmp_path, name):
    ctx, a, _, _ = await plugin_context()
    identifier = await submit(ctx, a, tmp_path)
    task_server.update(result_type="application/zip", result_body=zipped([(name, "bad")]))
    result = await call(ctx, a, "result", task_id=identifier)
    assert not result["ok"] and result["code"] in ("STORAGE_ERROR", "INVALID_RESPONSE")
    assert not (tmp_path / "storage" / identifier).exists()
    assert not list((tmp_path / "storage").glob("stage-*"))


async def test_host_filesystem_denial_and_unregistered_owner_precede_network(plugin_context, task_server, tmp_path):
    ctx, a, _, _ = await plugin_context()
    from dsh.fs.fs_local import FsError
    class DeniedFs:
        async def resolve(self, path, options):
            raise FsError("denied", "FS_PERMISSION_DENIED")
        async def readByteRange(self, *args):
            raise AssertionError("unreachable")
    ctx.set_service("fs", DeniedFs())
    denied = await ctx.get("tools").execute(ToolExecutionInput("deny", "mineru_submit",
        {"file_path": "one.pdf"}, agent=a, signal=None))
    assert denied.is_error and "denied" in denied.content[0]["text"]
    service = ctx.get("mineruWin7")
    from mineru_win7.errors import MinerUError
    impostor = SimpleNamespace(id=a.id, session=a.session)
    with pytest.raises(MinerUError, match="registered"):
        await service.execute("list", {}, SimpleNamespace(agent=impostor, session=a.session, signal=None))
    assert task_server["requests"] == []


async def test_snapshot_change_rejected_before_post(plugin_context, task_server, tmp_path):
    ctx, a, _, _ = await plugin_context()
    fs = ctx.get("fs")
    original = fs.readByteRange
    path = tmp_path / "changed.pdf"
    path.write_bytes(b"before")
    async def changed(*args):
        result = await original(*args)
        path.write_bytes(b"changed-source")
        return result
    fs.readByteRange = changed
    result = await call(ctx, a, "submit", file_path=str(path))
    assert not result["ok"] and result["code"] == "FILE_ACCESS_ERROR"
    assert task_server["requests"] == []


async def test_forget_cannot_delete_an_inflight_submission(plugin_context, task_server, tmp_path):
    ctx, a, b, _ = await plugin_context()
    source = tmp_path / "pending.pdf"
    source.write_bytes(b"%PDF")
    task_server["stall_submit"] = True
    pending = asyncio.create_task(call(ctx, a, "submit", file_path=str(source)))
    try:
        deadline = asyncio.get_running_loop().time() + 3
        while not task_server["requests"]:
            assert asyncio.get_running_loop().time() < deadline
            await asyncio.sleep(0.01)
        identifier = (await call(ctx, a, "list"))["tasks"][0]["task_id"]
        assert (await call(ctx, b, "forget", task_id=identifier))["code"] == "TASK_NOT_FOUND"
        assert (await call(ctx, a, "forget", task_id=identifier))["code"] == "TASK_BUSY"
    finally:
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
    assert not ctx.get("mineruWin7").submitting
    assert (await call(ctx, a, "forget", task_id=identifier))["ok"]


async def test_agent_scoped_filesystem_denial_precedes_root_access(plugin_context, task_server):
    from dsh.fs.fs_local import FsError
    ctx, a, _, _ = await plugin_context()
    scoped = ctx.extend()
    class DeniedFs:
        async def resolve(self, path, options):
            raise FsError("scoped access denied", "FS_PERMISSION_DENIED")
        async def readByteRange(self, *args):
            raise AssertionError("unreachable")
    scoped.set_service("fs", DeniedFs())
    a.ctx = scoped
    result = await ctx.get("tools").execute(ToolExecutionInput("scoped", "mineru_submit",
        {"file_path": "private.pdf"}, agent=a, signal=None))
    assert result.is_error and "scoped access denied" in result.content[0]["text"]
    assert task_server["requests"] == []


async def test_bounded_task_and_manifest_pagination(plugin_context, task_server, tmp_path):
    ctx, a, b, _ = await plugin_context()
    first = await submit(ctx, a, tmp_path)
    await submit(ctx, a, tmp_path)
    page = await call(ctx, a, "list", limit=1)
    assert len(page["tasks"]) == 1 and not page["eof"] and page["next_offset"] == 1
    next_page = await call(ctx, a, "list", offset=page["next_offset"], limit=1)
    assert next_page["eof"] and next_page["tasks"][0]["task_id"] != page["tasks"][0]["task_id"]
    entries = [("document/%03d.md" % i, "text") for i in range(105)]
    task_server.update(result_type="application/zip", result_body=zipped(entries))
    saved = await call(ctx, a, "result", task_id=first)
    assert saved["ok"] and saved["task"]["artifact_count"] == 105
    assert saved["task"]["manifest_truncated"] and len(saved["task"]["artifacts"]) == 100
    manifest = await call(ctx, a, "files", task_id=first, limit=100)
    remainder = await call(ctx, a, "files", task_id=first, offset=manifest["next_offset"])
    assert len(manifest["files"]) == 100 and not manifest["eof"]
    assert len(remainder["files"]) == 5 and remainder["eof"]
    assert (await call(ctx, b, "files", task_id=first))["code"] == "TASK_NOT_FOUND"
    assert (await call(ctx, a, "files", task_id=first, limit=101))["code"] == "INVALID_ARGUMENT"
    assert "artifacts" not in (await call(ctx, a, "list"))["tasks"][0]


async def test_wait_completion_and_jobs_notification_and_kill(plugin_context, task_server, tmp_path):
    from dsh.jobs.local import LocalJobRegistry
    from dsh.jobs.tool_jobs import ToolJobsPlugin
    ctx, a, _, _ = await plugin_context()
    await ctx.plugin(LocalJobRegistry)
    await ctx.plugin(ToolJobsPlugin)
    identifier = await submit(ctx, a, tmp_path)
    task_server["status"] = "completed"
    result = await call(ctx, a, "wait", task_id=identifier, background=True)
    assert result["ok"], result
    deadline = asyncio.get_running_loop().time() + 3
    while ctx.get("jobs").get(result["job_id"], caller=a)["status"] == "running":
        assert asyncio.get_running_loop().time() < deadline
        await asyncio.sleep(0.01)
    assert ctx.get("jobs").get(result["job_id"], caller=a)["status"] == "completed"
    assert a.inbox.next_turn or a.inbox.next_step
    task_server["status"] = "processing"
    result = await call(ctx, a, "wait", task_id=identifier, background=True)
    assert ctx.get("jobs").kill(result["job_id"], caller=a) == "requested"
    assert (await ctx.get("jobs").wait(result["job_id"], 3000, caller=a))["status"] == "killed"
    assert all(method != "DELETE" for method, _, _, _ in task_server["requests"])


@pytest.mark.parametrize("mode", ["transient", "permanent", "cancel"])
async def test_windows_publish_contention_is_bounded_without_network_retry(plugin_context, task_server, tmp_path, monkeypatch, mode):
    import mineru_win7.service as service_module
    ctx, a, _, _ = await plugin_context()
    identifier = await submit(ctx, a, tmp_path)
    rename = service_module.os.rename
    attempts = []
    signal = asyncio.Event()
    def contended(source, destination):
        attempts.append(source)
        if mode == "permanent" or len(attempts) <= 2:
            if mode == "cancel":
                signal.set()
            error = PermissionError("Windows fixture: file is temporarily busy")
            error.winerror = 32
            raise error
        return rename(source, destination)
    monkeypatch.setattr(service_module.os, "rename", contended)
    result = await ctx.get("tools").execute(ToolExecutionInput("busy", "mineru_result",
        {"task_id": identifier}, agent=a, signal=signal))
    if mode == "cancel":
        assert result.is_error  # The host abort contract overrides tool output.
    else:
        assert not result.is_error
        assert result.value["ok"] == (mode == "transient")
    assert len(attempts) == {"transient": 3, "permanent": 6, "cancel": 1}[mode]
    assert sum(path.endswith("/result") for _, path, _, _ in task_server["requests"]) == 1
    assert not list((tmp_path / "storage").glob("stage-*"))
