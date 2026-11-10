"""Exercise the real package installer, canonical boot and scoped tools."""

import asyncio
import json
import sys
import zipfile
from pathlib import Path

import pytest

from apps.cli import plugin as plugin_cli
from dsh.boot.profile import init_profile, read_profile_manifest
from dsh.boot.profile_boot import run_profile
from dsh.boot.python_package import validate_sources
from dsh.core.tools import ToolExecutionInput


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
async def test_zip_install_canonical_boot_all_tools_unload_and_remove(tmp_path, monkeypatch):
    monkeypatch.delenv("MINERU_BASE_URL", raising=False)
    home = tmp_path / "home"
    monkeypatch.setenv("DSH_HOME", str(home))
    profile = home / "profiles" / "mineru-scaffold-test"
    init_profile(str(profile), [], "startup")
    (profile / "cordis.patch.yml").write_text(
        "- insert:\n"
        "    - id: system-prompt\n      name: '@deepseek-ai/dsh-system-prompt'\n"
        "    - id: tools\n      name: '@deepseek-ai/dsh-tools'\n",
        encoding="utf-8",
    )
    assert validate_sources(str(PROJECT_ROOT))["name"] == "dsh-mineru-win7"
    archive_path = tmp_path / "mineru-scaffold.zip"
    assert plugin_cli.run_plugin("mineru-scaffold-test", ["pack", str(PROJECT_ROOT), str(archive_path)]) == 0
    manifest = json.loads((PROJECT_ROOT / "package.json").read_text(encoding="utf-8"))
    with zipfile.ZipFile(str(archive_path)) as archive:
        assert set(archive.namelist()) == set(manifest["dsh"]["release"]["files"])
    assert plugin_cli.run_plugin("mineru-scaffold-test", ["add", str(archive_path)]) == 0
    before_path = list(sys.path)
    runtime = await run_profile(dict(profile="mineru-scaffold-test", dshHome=str(home),
                                     args=[], wait_for_exit=False))
    ctx = runtime["ctx"]
    try:
        assert list(sys.path) == before_path
        service = ctx.get("mineruWin7")
        assert service is not None
        for operation, arguments in (("health", {}), ("submit", {"file_path": "never-read.pdf"}),
                                     ("status", {"task_id": "one"}), ("result", {"task_id": "one"})):
            outcome = await ctx.get("tools").execute(ToolExecutionInput(
                "scaffold-" + operation, "mineru_" + operation, arguments, signal=asyncio.Event()))
            assert not outcome.is_error, outcome.error
            assert outcome.value["ok"] is False
            assert outcome.value["code"] == "NOT_CONFIGURED"
        entry = next(entry for entry in ctx.loader.entries if entry.options.get("id") == "mineru-win7")
        await entry.fiber.dispose()
        await entry.fiber.await_settled()
        assert service.provider.closed
        assert ctx.get("mineruWin7") is None
        for operation in ("health", "submit", "status", "result"):
            missing = await ctx.get("tools").execute(ToolExecutionInput(
                "unloaded-" + operation, "mineru_" + operation, {}, signal=asyncio.Event()))
            assert missing.is_error and missing.error["info"]["code"] == "UNKNOWN_TOOL"
    finally:
        await ctx.fiber.dispose()
        await ctx.fiber.await_settled()
    assert plugin_cli.run_plugin("mineru-scaffold-test", ["remove", "dsh-mineru-win7"]) == 0
    assert read_profile_manifest("dsh", str(profile))["dsh"]["profile"]["bundles"] == []


@pytest.mark.asyncio
async def test_configured_provider_explicitly_refuses_network_and_file_io(monkeypatch):
    from mineru_win7.config import MinerUConfig
    from mineru_win7.errors import PendingImplementation, ServiceClosed
    from mineru_win7.providers.legacy_tasks import LegacyTasksProvider

    provider = LegacyTasksProvider(MinerUConfig.from_mapping({"baseURL": "http://unused.invalid/mineru/"}, {}))
    for method, args in ((provider.health, ()), (provider.submit, ("nonexistent.pdf",)),
                         (provider.status, ("one",)), (provider.result, ("one",))):
        with pytest.raises(PendingImplementation):
            await method(*args)
    provider.close()
    with pytest.raises(ServiceClosed):
        await provider.health()
