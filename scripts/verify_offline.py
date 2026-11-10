"""Verify a plugin ZIP in source or an actual extracted Portable; loopback only."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import time
import zipfile

from offline_fixture import OfflineMinerU

SCRIPTS = Path(__file__).resolve().parent


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            value.update(block)
    return value.hexdigest()


def extract(archive, output):
    with zipfile.ZipFile(str(archive)) as source:
        entries = source.infolist()
        expanded = sum(item.file_size for item in entries)
        if expanded > 1073741824 or len(entries) > 30000:
            raise ValueError("Portable fixture exceeds extraction budget")
        if shutil.disk_usage(str(output.parent)).free < expanded * 2 + 104857600:
            raise ValueError("Not enough disk space for owned Portable fixture")
        for item in entries:
            original = item.orig_filename
            path = PurePosixPath(original)
            if (original != item.filename or path.is_absolute() or ".." in path.parts or "\\" in original or ":" in original or
                    (item.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError("Unsafe Portable member")
        source.extractall(str(output))
    root = output / "dsh-win7-portable"
    if not (root / "python.exe").is_file() or not (root / "dsh.py").is_file():
        raise ValueError("Expected dsh-win7-portable/python.exe and dsh.py")
    return root


def clean_environment():
    environment = dict(os.environ)
    for key in list(environment):
        if key.startswith(("DEEPSEEK_", "OPENAI_", "DSH_", "MINERU_")) or key in ("PYTHONPATH", "PYTHONHOME"):
            environment.pop(key)
    environment["PYTHONUTF8"] = "1"
    return environment


async def command(argv, output, environment, timeout=180):
    with output.open("wb") as log:
        process = await asyncio.create_subprocess_exec(*argv, stdout=log, stderr=log, env=environment)
        try:
            status = await asyncio.wait_for(process.wait(), timeout)
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise
    if status:
        raise RuntimeError("Command failed (%s); see %s" % (status, output))


async def run(args):
    output, plugin = Path(args.output).resolve(), Path(args.plugin_archive).resolve()
    if not plugin.is_file():
        raise ValueError("Plugin archive not found")
    if not args.no_browser and not all((args.node, args.chromium, args.playwright_module)):
        raise ValueError("Provide --node, --chromium and --playwright-module, or explicitly use --no-browser")
    output.mkdir(parents=True, exist_ok=False)
    receipt = dict(kind="offline-plugin-journey", passed=False, scope="Local protocol fixture only; no OCR, LLM, Win7 hardware or host release gate",
        plugin_archive=str(plugin), plugin_sha256=digest(plugin), phases=[], scripts={path.name:digest(path) for path in
            list(SCRIPTS.glob("offline_*.*")) + [SCRIPTS / "verify_offline.py", SCRIPTS / "verify_live.py"]})
    fixture = None
    started = time.monotonic()
    try:
        if args.portable:
            archive = Path(args.portable).resolve()
            receipt.update(portable_archive=str(archive), portable_sha256=digest(archive))
            root = extract(archive, output / "extracted")
            python = root / "python.exe"
            provenance = root / "build-provenance.json"
            if provenance.exists():
                receipt["portable_provenance"] = json.loads(provenance.read_text(encoding="utf-8"))
        else:
            root, python = Path(args.host_root).resolve(), Path(args.python or sys.executable).resolve()
        fixture = await OfflineMinerU().start()
        environment = clean_environment()
        for phase in ("fresh", "cold", "removed"):
            phase_output = output / phase
            phase_output.mkdir()
            before = len(fixture.requests)
            argv = [str(python), str(SCRIPTS / "offline_worker.py"), "--root", str(root), "--home", str(output / "home"),
                "--output", str(phase_output), "--plugin-archive", str(plugin), "--base-url", fixture.base_url, "--phase", phase]
            log = (phase_output / "worker.log").open("wb")
            process = await asyncio.create_subprocess_exec(*argv, stdout=log, stderr=log, env=environment, cwd=str(root))
            try:
                deadline = time.monotonic() + 90
                while not (phase_output / "ready.json").exists():
                    if process.returncode is not None or time.monotonic() >= deadline:
                        raise RuntimeError("Worker did not become ready; see %s" % (phase_output / "worker.log"))
                    await asyncio.sleep(0.1)
                if not args.no_browser:
                    await command([args.node, str(SCRIPTS / "offline_browser.cjs"), str(phase_output), args.chromium,
                        args.playwright_module, phase], phase_output / "browser.log", environment)
                (phase_output / "stop").touch()
                status = await asyncio.wait_for(process.wait(), 45)
                if status:
                    raise RuntimeError("Worker failed; see %s" % (phase_output / "worker.log"))
            finally:
                (phase_output / "stop").touch()
                if process.returncode is None:
                    try:
                        await asyncio.wait_for(process.wait(), 35)
                    except asyncio.TimeoutError:
                        process.kill()
                        await process.wait()
                log.close()
            phase_receipt = json.loads((phase_output / "receipt.json").read_text(encoding="utf-8"))
            assert phase_receipt["passed"], phase
            if phase != "fresh":
                assert len(fixture.requests) == before, "Cold cache/uninstall unexpectedly used remote HTTP"
                phase_receipt["checks"].append("zero remote HTTP during cold/uninstall")
            phase_receipt["requests"] = len(fixture.requests) - before
            receipt["phases"].append(phase_receipt)
            print("PASS %s (%s-bit, %d HTTP requests)" % (phase, phase_receipt["bitness"], phase_receipt["requests"]), flush=True)
        assert not any(row["method"] == "DELETE" for row in fixture.requests)
        assert sum(row["method"] == "POST" and row["path"] == "/mineru/tasks" for row in fixture.requests) == (10 if not args.no_browser else 7), "Unexpected submission retry or missing submission"
        assert digest(plugin) == receipt["plugin_sha256"], "Plugin ZIP changed during verification"
        if args.portable:
            assert digest(Path(args.portable).resolve()) == receipt["portable_sha256"], "Portable ZIP changed during verification"
        for name, expected in receipt["scripts"].items():
            assert digest(SCRIPTS / name) == expected, "Observer changed during verification"
        receipt["passed"] = True
    finally:
        if fixture is not None:
            await fixture.close()
            (output / "requests.json").write_text(json.dumps(fixture.requests, indent=2), encoding="utf-8")
        receipt["wall_seconds"] = round(time.monotonic() - started, 3)
        (output / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="Fresh short owned directory; includes private local Web connection tokens")
    parser.add_argument("--plugin-archive", required=True)
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--portable", help="Actual existing Portable ZIP; never rebuilt or modified")
    target.add_argument("--host-root", default=str(SCRIPTS.parents[2]))
    parser.add_argument("--python", help="Source-host Python; Portable always uses its extracted python.exe")
    parser.add_argument("--node")
    parser.add_argument("--chromium")
    parser.add_argument("--playwright-module", help="Absolute Playwright module directory or installed module name")
    parser.add_argument("--no-browser", action="store_true")
    asyncio.run(run(parser.parse_args()))
