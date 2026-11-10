"""Public offline test entry points and fixture wire behavior."""
import io
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest
from mineru_win7.config import MinerUConfig
from mineru_win7.providers.legacy_tasks import LegacyTasksProvider
from mineru_win7.http import TransportError, ResponseError


@pytest.fixture
def offline_modules(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    import offline_fixture
    import verify_offline
    return offline_fixture, verify_offline


async def test_offline_fixture_serves_real_multipart_zip_json_and_failure_states(offline_modules):
    fixture_module, _ = offline_modules
    server = await fixture_module.OfflineMinerU().start()
    provider = LegacyTasksProvider(MinerUConfig(base_url=server.base_url))
    async def submit(name, zipped):
        return await provider.submit(SimpleNamespace(name=name, stream=io.BytesIO(b"%PDF probe"), size=10),
                                     dict(response_format_zip="true" if zipped else "false"))
    try:
        assert (await provider.health())["data"]["gateway"] == "LOCAL PROTOCOL FIXTURE ONLY"
        for zipped in (True, False):
            task = await submit("中文.pdf", zipped)
            server.tasks[task["task_id"]]["created"] -= 1
            response = await provider.result(task["task_id"])
            try:
                assert response.status == 200
                if zipped:
                    with zipfile.ZipFile(response.body) as archive:
                        assert archive.read("converted/ocr/converted.md").decode("utf-8") == fixture_module.TEXT
                else:
                    assert response.json(1048576)["results"]["converted-pdf"]["md_content"] == fixture_module.TEXT
            finally:
                response.close()
        for name, code in (("slow.pdf", 202), ("failed.pdf", 409)):
            task = await submit(name, True)
            response = await provider.result(task["task_id"])
            assert response.status == code
            response.close()
        with pytest.raises((TransportError, ResponseError)):
            await submit("disconnect.pdf", True)
        assert len(server.tasks) == 5
        assert len({row["task_id"] for row in [server.payload(key) for key in server.tasks]}) == 5
    finally:
        provider.close()
        await server.close()


@pytest.mark.parametrize("name", ["../escape", "/absolute", "dsh-win7-portable/x:y", "dsh-win7-portable/dir\\file"])
def test_portable_observer_rejects_unsafe_archive_members(tmp_path, offline_modules, name):
    _, observer = offline_modules
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(str(archive), "w") as stream:
        info = zipfile.ZipInfo(name)
        info.filename = name
        stream.writestr(info, b"unsafe")
    with pytest.raises(ValueError, match="Unsafe"):
        observer.extract(archive, tmp_path / "extracted")
    assert not (tmp_path / "extracted").exists()


async def test_offline_observer_requires_browser_inputs_and_preserves_existing_output(tmp_path, offline_modules):
    _, observer = offline_modules
    archive = tmp_path / "plugin.zip"
    archive.write_bytes(b"not used before validation")
    output = tmp_path / "owned-output"
    args = SimpleNamespace(plugin_archive=str(archive), output=str(output), no_browser=False,
        node=None, chromium=None, playwright_module=None)
    with pytest.raises(ValueError, match="Provide"):
        await observer.run(args)
    assert not output.exists()
    output.mkdir()
    sentinel = output / "preserve.txt"
    sentinel.write_text("original", encoding="utf-8")
    args.no_browser = True
    with pytest.raises(FileExistsError):
        await observer.run(args)
    assert sentinel.read_text(encoding="utf-8") == "original"
