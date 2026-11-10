import asyncio
import io
import json
import stat
import zipfile

import pytest
from test_workflow import call, submit, zipped


@pytest.mark.parametrize("change", ["symlink", "case-duplicate", "inflate", "many", "bad-json", "invalid-image"])
async def test_result_resource_and_identity_limits(plugin_context, task_server, tmp_path, change):
    ctx, a, _, _ = await plugin_context(maxFiles=2, maxExtractBytes=2048)
    identifier = await submit(ctx, a, tmp_path)
    if change == "symlink":
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            info = zipfile.ZipInfo("link")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, "../escape")
        body = stream.getvalue()
    elif change == "case-duplicate":
        body = zipped([("A.md", "one"), ("a.md", "two")])
    elif change == "inflate":
        body = zipped([("large.md", "x" * 4096)])
    elif change == "many":
        body = zipped([("%s.md" % i, "x") for i in range(3)])
    elif change == "bad-json":
        body = b'{"results": {"one": {"md_content": 42}}}'
    else:
        body = b'{"results": {"one": {"images": {"image.png": "https://container.invalid/img"}}}}'
    task_server.update(result_type="application/json" if change in ("bad-json", "invalid-image") else "application/zip", result_body=body)
    result = await call(ctx, a, "result", task_id=identifier)
    assert not result["ok"] and result["code"] == "INVALID_RESPONSE", result
    assert not (tmp_path / "storage" / identifier).exists()


async def test_upload_budget_office_rules_and_no_file_read_before_owner(plugin_context, task_server, tmp_path):
    ctx, a, _, _ = await plugin_context(maxUploadBytes=3)
    path = tmp_path / "oversize.pdf"
    path.write_bytes(b"1234")
    assert (await call(ctx, a, "submit", file_path=str(path)))["code"] == "FILE_ACCESS_ERROR"
    legacy = tmp_path / "old.doc"
    legacy.write_bytes(b"123")
    assert (await call(ctx, a, "submit", file_path=str(legacy), office_mode="native"))["code"] == "INVALID_ARGUMENT"
    assert task_server["requests"] == []


async def test_task_quota_does_not_block_result_and_forget_releases_slot(plugin_context, task_server, tmp_path):
    ctx, a, _, _ = await plugin_context(maxTasks=1)
    identifier = await submit(ctx, a, tmp_path)
    path = tmp_path / "next.pdf"
    path.write_bytes(b"123")
    assert (await call(ctx, a, "submit", file_path=str(path)))["code"] == "STORAGE_ERROR"
    assert (await call(ctx, a, "result", task_id=identifier))["ok"]
    assert (await call(ctx, a, "forget", task_id=identifier))["ok"]
    assert (await call(ctx, a, "submit", file_path=str(path)))["ok"]


async def test_unload_cancels_inflight_upload_and_preserves_ambiguous_submission(plugin_context, task_server, tmp_path):
    ctx, a, _, fiber = await plugin_context()
    task_server["stall_submit"] = True
    source = tmp_path / "one.pdf"
    source.write_bytes(b"%PDF")
    from types import SimpleNamespace
    execution = SimpleNamespace(agent=a, session=a.session, signal=asyncio.Event())
    service = ctx.get("mineruWin7")
    upload = asyncio.create_task(service.execute("submit", {"file_path": str(source)}, execution))
    deadline = asyncio.get_running_loop().time() + 3
    while not task_server["requests"]:
        assert asyncio.get_running_loop().time() < deadline
        await asyncio.sleep(0.01)
    await asyncio.wait_for(fiber.dispose(), 3)
    await fiber.await_settled()
    await asyncio.gather(upload, return_exceptions=True)
    assert not service.active and not service.provider.http._requests
    ctx2, a2, _, _ = await plugin_context()
    result = await call(ctx2, a2, "list")
    assert result["tasks"][0]["status"] == "submission-unknown"


async def test_status_404_and_wait_deadline_and_local_stop(plugin_context, task_server, tmp_path):
    ctx, a, _, _ = await plugin_context(waitTimeoutSeconds=1)
    identifier = await submit(ctx, a, tmp_path)
    task_server["status_code"] = 404
    assert (await call(ctx, a, "status", task_id=identifier))["code"] == "TASK_NOT_FOUND"
    task_server.pop("status_code")
    result = await call(ctx, a, "wait", task_id=identifier)
    assert result["code"] == "REQUEST_TIMEOUT"
    assert all(row[0] != "DELETE" for row in task_server["requests"])
