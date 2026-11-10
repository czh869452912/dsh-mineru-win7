"""Child process observer; imports the selected source/extracted host exclusively."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_live import probes


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


async def main(args):
    root, output, home = Path(args.root).resolve(), Path(args.output).resolve(), Path(args.home).resolve()
    sys.path.insert(0, str(root))
    os.chdir(str(root))
    os.environ.update(DSH_HOME=str(home), DSH_TELEMETRY_MODE="DISABLED", MINERU_BASE_URL=args.base_url)
    from apps.cli.plugin import run_plugin
    from dsh.boot.profile_boot import run_profile
    from dsh.core.tools import ToolExecutionInput
    from dsh.jobs.tool_jobs import ToolJobsPlugin
    import dsh
    assert Path(dsh.__file__).resolve().parent.parent == root, "Host import escaped selected runtime"
    receipt = dict(phase=args.phase, checks=[], python=sys.version, executable=sys.executable,
                   bitness=struct.calcsize("P") * 8, host_module=dsh.__file__, pid=os.getpid(), passed=False)
    runtime = None
    state_path = home.parent / "state.json"
    async def browser_checkpoint(ctx, config):
        config["url"] = ctx.connection.authenticated_url("http://127.0.0.1:%d" % ctx.webServer.port)
        write(output / "ready.json", config)
        print("READY", flush=True)
        deadline = time.monotonic() + 180
        while not (output / "stop").exists():
            assert time.monotonic() < deadline, "browser completion deadline"
            await asyncio.sleep(0.1)
    try:
        if args.phase == "fresh":
            assert run_plugin("web", ["add", args.plugin_archive]) == 0
        elif args.phase == "removed":
            assert run_plugin("web", ["remove", "dsh-mineru-win7"]) == 0
        runtime = await run_profile(dict(profile="web", dshHome=str(home), args=["--no-open", "--port", "0"], waitForExit=False))
        ctx = runtime["ctx"]
        if args.phase == "removed":
            assert ctx.get("mineruWin7") is None and ctx.get("mineruPanel") is None
            assert "dsh-mineru-win7" not in {row["id"] for row in ctx.get("clientModules").graph()["entries"]}
            state = json.loads(state_path.read_text(encoding="utf-8"))
            assert Path(state["retained_file"]).is_file()
            assert hashlib.sha256(Path(state["retained_file"]).read_bytes()).hexdigest() == state["retained_sha256"]
            receipt["checks"] += ["CLI uninstall", "services and client graph removed", "saved artifacts retained"]
            await browser_checkpoint(ctx, {})
        else:
            # Quiet delivery exercises the real bundled jobs controller without
            # waking an LLM. Minimal sessions intentionally omit that controller.
            await ctx.plugin(ToolJobsPlugin, config=dict(completionDelivery="quiet"))
            for identifier in ("mineru-offline-a", "mineru-offline-b"):
                if args.phase == "fresh":
                    await ctx.sessionController.create(dict(sessionId=identifier, cwd=str(home.parent / "probes"), agentPreset="minimal"))
                    await ctx.sessionController.rename(dict(sessionId=identifier, title=identifier))
                else:
                    resolved = await ctx.sessionController.resolveAgent(identifier)
                    assert "agent" in resolved, resolved
            a, b = [ctx.agents.get(identifier) for identifier in ("mineru-offline-a", "mineru-offline-b")]
            module = sys.modules[type(ctx.get("mineruWin7")).__module__]
            assert str(Path(module.__file__).resolve()).lower().startswith(str(home).lower()), module.__file__
            receipt["plugin_module"] = module.__file__
            receipt["checks"].append("installed snapshot imports; no source plugin import")
            async def call(agent, operation, values=None, expected=None, raw=False):
                name = operation if operation.startswith("job_") else "mineru_" + operation
                result = await agent.ctx.get("tools").execute(ToolExecutionInput("offline-" + operation, name, values or {},
                    agent=agent, signal=asyncio.Event()))
                if raw:
                    return result
                assert not result.is_error, (operation, result.error)
                value = result.value
                assert value.get("code") == expected if expected else value.get("ok"), (operation, value)
                return value
            async def job_finished(identifier, state):
                deadline = time.monotonic() + 15
                while ctx.jobs.get(identifier, caller=a)["status"] in ("running", "stopping"):
                    assert time.monotonic() < deadline, "job deadline"
                    await asyncio.sleep(0.05)
                assert ctx.jobs.get(identifier, caller=a)["status"] == state
            if args.phase == "fresh":
                probe_dir = home.parent / "probes"
                probe_dir.mkdir(exist_ok=True)
                sources = probes(probe_dir)
                tasks = []
                await call(a, "health")
                for source, format_ in zip(sources, ("zip", "json", "zip")):
                    submitted = await call(a, "submit", dict(file_path=str(source), format=format_))
                    task_id = submitted["task"]["task_id"]
                    await call(b, "status", dict(task_id=task_id), "TASK_NOT_FOUND")
                    result = await call(a, "wait", dict(task_id=task_id, timeout_seconds=15))
                    text = await call(a, "read", dict(task_id=task_id, limit=100))
                    assert text["text"].startswith("# 本地协议验证") and not text["eof"]
                    listing = await call(a, "files", dict(task_id=task_id))
                    for item in listing["files"]:
                        file = Path(result["task"]["directory"]) / item["name"]
                        assert file.stat().st_size == item["size"]
                        assert hashlib.sha256(file.read_bytes()).hexdigest() == item["sha256"]
                    tasks.append(result["task"])
                receipt["checks"] += ["PDF ZIP / PNG JSON / DOCX ZIP", "owner isolation", "actual artifacts and hashes", "bounded Markdown read"]
                background = probe_dir / "background.pdf"
                shutil.copyfile(str(sources[0]), str(background))
                identifier = (await call(a, "submit", dict(file_path=str(background))))["task"]["task_id"]
                job = (await call(a, "wait", dict(task_id=identifier, background=True)))["job_id"]
                await job_finished(job, "completed")
                messages = (getattr(a.inbox, "nextTurn", getattr(a.inbox, "next_turn", [])) +
                            getattr(a.inbox, "nextStep", getattr(a.inbox, "next_step", [])))
                assert any(job in json.dumps(message) and "tool-jobs" in json.dumps(message) for message in messages), "missing completion notification"
                assert (await call(b, "job_output", dict(job_id=job), raw=True)).is_error
                output_result = await call(a, "job_output", dict(job_id=job), raw=True)
                assert not output_result.is_error and output_result.value["job"]["status"] == "completed"
                slow = probe_dir / "slow.pdf"
                shutil.copyfile(str(sources[0]), str(slow))
                identifier = (await call(a, "submit", dict(file_path=str(slow))))["task"]["task_id"]
                await call(a, "result", dict(task_id=identifier), "RESULT_NOT_READY")
                job = (await call(a, "wait", dict(task_id=identifier, background=True)))["job_id"]
                killed = await call(a, "job_kill", dict(job_id=job), raw=True)
                assert not killed.is_error
                await job_finished(job, "killed")
                assert (await call(a, "status", dict(task_id=identifier)))["task"]["status"] == "processing"
                failed = probe_dir / "failed.pdf"
                shutil.copyfile(str(sources[0]), str(failed))
                identifier = (await call(a, "submit", dict(file_path=str(failed))))["task"]["task_id"]
                await call(a, "wait", dict(task_id=identifier), "TASK_FAILED")
                await call(a, "result", dict(task_id=identifier), "TASK_FAILED")
                disconnected = probe_dir / "disconnect.pdf"
                shutil.copyfile(str(sources[0]), str(disconnected))
                unknown = await call(a, "submit", dict(file_path=str(disconnected)), raw=True)
                assert not unknown.is_error and not unknown.value["ok"] and unknown.value["task_id"]
                await call(a, "status", dict(task_id=unknown.value["task_id"]), "SUBMISSION_UNKNOWN")
                receipt["checks"] += ["background completion notification", "cross-owner job denied", "job kill keeps remote processing", "202/409", "lost POST acknowledgement not retried"]
                retained = Path(tasks[0]["directory"]) / tasks[0]["artifacts"][0]["name"]
                write(state_path, dict(tasks=tasks, retained_file=str(retained), retained_sha256=hashlib.sha256(retained.read_bytes()).hexdigest()))
                await browser_checkpoint(ctx, dict(source=str(sources[0]), slow=str(slow), failed=str(failed), owner=a.id, other=b.id))
            else:
                state = json.loads(state_path.read_text(encoding="utf-8"))
                for task in state["tasks"]:
                    await call(a, "result", dict(task_id=task["task_id"]), "RESULT_CACHED")
                    await call(a, "read", dict(task_id=task["task_id"], limit=100))
                    await call(b, "read", dict(task_id=task["task_id"]), "TASK_NOT_FOUND")
                forgotten = state["tasks"][-1]
                await call(a, "forget", dict(task_id=forgotten["task_id"]))
                assert not Path(forgotten["directory"]).exists()
                assert Path(state["retained_file"]).exists()
                receipt["checks"] += ["separate process cold owner recovery", "all saved results cached", "cold cross-owner read denied", "forget only chosen artifacts"]
                await browser_checkpoint(ctx, dict(owner=a.id, other=b.id, cached_task=state["tasks"][0]["task_id"]))
            for agent in (a, b):
                await agent.session.flush()
        receipt["passed"] = True
    finally:
        try:
            if runtime is not None:
                runtime["shutdown"].shutdown(0)
                await asyncio.wait_for(runtime["shutdown"].wait(), 30)
        finally:
            write(output / "receipt.json", receipt)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("root", "output", "home", "plugin-archive", "base-url"):
        parser.add_argument("--" + option, required=True)
    parser.add_argument("--phase", choices=("fresh", "cold", "removed"), required=True)
    asyncio.run(main(parser.parse_args()))
