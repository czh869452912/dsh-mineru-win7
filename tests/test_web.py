"""Installed original Web graph and strict Remote/tool policy boundary."""
import asyncio
import json
from pathlib import Path

import pytest
from apps.cli import plugin as cli
from canonical_web_fixture import web_context, close_web_context
from dsh.core.abort import NEVER_ABORTED
from dsh.typert.dispatch import RemoteDispatcher, TypertGatewayError

PROJECT = Path(__file__).resolve().parents[1]


async def info(ctx):
    return json.loads(await RemoteDispatcher(ctx).invoke(dict(namespace="mineruPanel", method="info", args={}, signal=NEVER_ABORTED)))


async def run(ctx, agent, action, arguments):
    return json.loads(await RemoteDispatcher(ctx).invoke(dict(namespace="mineruPanel", method="run",
        args=dict(agentId=agent.id, operation=action, arguments=json.dumps(arguments)), signal=NEVER_ABORTED)))


async def test_installed_web_graph_remote_policy_unload_and_cold_restart(tmp_path, monkeypatch, task_server):
    home = tmp_path / "web-home"
    monkeypatch.setenv("DSH_HOME", str(home))
    monkeypatch.setenv("MINERU_BASE_URL", task_server["base"])
    ctx = await web_context(home)
    await close_web_context(ctx)
    archive = tmp_path / "mineru.zip"
    assert cli.run_plugin("web", ["pack", str(PROJECT), str(archive)]) == 0
    assert cli.run_plugin("web", ["add", str(archive)]) == 0
    for generation in range(2):
        ctx = await web_context(home)
        try:
            assert "dsh-mineru-win7" in {row["id"] for row in ctx.get("clientModules").graph()["entries"]}
            assert (await info(ctx))["baseURL"] == task_server["base"]
            await ctx.get("sessionController").create(dict(sessionId="web-owner", cwd=str(tmp_path), agentPreset="minimal"))
            a = ctx.get("agents").get("web-owner")
            listed = await run(ctx, a, "list", {})
            assert listed["ok"], listed
            assert (await info(ctx))["agents"][-1]["id"] == a.id
            denied = await run(ctx, a, "submit", {"file_path": "bad.exe"})
            assert not denied["ok"]
            with pytest.raises(ValueError, match="Invalid"):
                await run(ctx, a, "arbitrary_tool", {})
            if generation == 0:
                entry = next(row for row in ctx.loader.entries if row.options.get("name") == "dsh-mineru-win7")
                await entry.fiber.dispose()
                await entry.fiber.await_settled()
                for _ in range(20):
                    await asyncio.sleep(0)
                assert ctx.get("mineruPanel") is None and ctx.get("mineruWin7") is None
                with pytest.raises(TypertGatewayError):
                    await info(ctx)
        finally:
            await close_web_context(ctx)
    assert cli.run_plugin("web", ["remove", "dsh-mineru-win7"]) == 0
