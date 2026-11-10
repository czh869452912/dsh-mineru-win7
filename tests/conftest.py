"""Develop against a selected host; reuse its short owned pytest workspace."""

import os
import asyncio
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOST_ROOT = Path(os.environ.get("DSH_HOST_ROOT", str(PROJECT_ROOT.parents[1]))).resolve()
if not (HOST_ROOT / "dsh" / "plugin_api.py").is_file():
    raise RuntimeError("Set DSH_HOST_ROOT to the DSH Win7 source checkout.")
sys.path.insert(0, str(HOST_ROOT))
sys.path.insert(0, str(HOST_ROOT / "tests"))
sys.path.insert(0, str(PROJECT_ROOT / "python"))

from scripts.process_artifact_retention import configure_pytest_workspace, prune_pytest_session


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    configure_pytest_workspace(config, HOST_ROOT / ".goose" / "out")


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    prune_pytest_session(session, exitstatus, HOST_ROOT / ".goose" / "out")


@pytest.fixture
async def http_server():
    servers, tasks, requests = [], set(), []

    async def start(response, stall=None):
        async def handle(reader, writer):
            task = asyncio.current_task()
            tasks.add(task)
            try:
                requests.append(await reader.readuntil(b"\r\n\r\n"))
                writer.write(response)
                await writer.drain()
                if stall is not None:
                    stall.set()
                    await reader.read()
            except (ConnectionError, asyncio.IncompleteReadError):
                pass
            finally:
                writer.close()
                tasks.discard(task)
        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        servers.append(server)
        return "http://127.0.0.1:%d/mineru/" % server.sockets[0].getsockname()[1]

    yield start, requests
    for server in servers:
        server.close()
        await server.wait_closed()
    pending = list(tasks)
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)


@pytest.fixture
async def task_server():
    import json
    state = dict(status="pending", requests=[], result_status=200, result_type="application/json",
                 result_body=json.dumps({"results": {"converted-pdf": {"md_content": "# 中文\nHello world\n"}}}).encode("utf-8"))
    tasks = set()

    async def handle(reader, writer):
        task = asyncio.current_task()
        tasks.add(task)
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            first, *lines = head.split(b"\r\n")
            method, path, _ = first.decode("ascii").split(" ")
            headers = dict(line.split(b": ", 1) for line in lines if b": " in line)
            body = await reader.readexactly(int(headers.get(b"Content-Length", b"0")))
            state["requests"].append((method, path, headers, body))
            payload = dict(task_id="remote-1", status=state["status"], file_names=["converted.pdf"],
                           status_url="http://container.invalid/private", result_url="http://container.invalid/secret")
            code, media = 200, "application/json"
            if method == "POST":
                code = state.get("submit_status", 202)
                if state.get("drop_submit"):
                    return
                if state.get("stall_submit"):
                    await reader.read()
                    return
            elif path.endswith("/result"):
                code, media = state["result_status"], state["result_type"]
                payload = state["result_body"]
            elif state.get("status_code"):
                code = state["status_code"]
            raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
            writer.write(("HTTP/1.1 %d Response\r\nContent-Type: %s\r\nContent-Length: %d\r\n\r\n" %
                          (code, media, len(raw))).encode("ascii") + raw)
            await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()
            tasks.discard(task)
    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    state["base"] = "http://127.0.0.1:%d/mineru/" % server.sockets[0].getsockname()[1]
    yield state
    server.close()
    await server.wait_closed()
    pending = list(tasks)
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)


@pytest.fixture
async def plugin_context(tmp_path, task_server, monkeypatch):
    from dsh.cordis.context import Context
    from dsh.core.tools import ToolsService
    from dsh.core.system_prompt.service import SystemPrompt
    from dsh.core.agent import Agent, AgentRegistry
    from dsh.core.session import Session
    from dsh.fs.fs_local import FsService
    from mineru_win7.plugin import MinerUPlugin
    contexts = []
    monkeypatch.setenv("DSH_HOME", str(tmp_path / "home"))

    async def create(**overrides):
        ctx = Context()
        contexts.append(ctx)
        ctx.set_service("tools", ToolsService(ctx))
        ctx.set_service("fs", FsService(cwd=str(tmp_path)))
        registry = AgentRegistry(ctx)
        ctx.set_service("agents", registry)
        await ctx.plugin(SystemPrompt)
        a = Agent(Session("one"), ctx=ctx)
        b = Agent(Session("two"), ctx=ctx)
        registry.register(a)
        registry.register(b)
        cfg = dict(baseURL=task_server["base"], storageDirectory=str(tmp_path / "storage"), pollIntervalSeconds=1)
        cfg.update(overrides)
        fiber = await ctx.plugin(MinerUPlugin, config=cfg)
        return ctx, a, b, fiber
    yield create
    for ctx in reversed(contexts):
        await ctx.fiber.dispose()
        await ctx.fiber.await_settled()
