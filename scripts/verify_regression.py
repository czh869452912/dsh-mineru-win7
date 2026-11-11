"""Run all plugin tests, binding executed source and JUnit to an exact ZIP."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile

from check_release import sha


def run(args):
    root = Path(__file__).resolve().parents[1]
    archive, output = args.archive.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    receipt = dict(passed=False, scope="all-plugin-tests", plugin_sha256=sha(archive), python=sys.version)
    started = time.monotonic()
    try:
        frozen = {}
        with zipfile.ZipFile(str(archive)) as stream:
            for name in stream.namelist():
                if stream.read(name) != (root / name).read_bytes():
                    raise ValueError("ZIP differs from working source: " + name)
                frozen[name] = sha(root / name)
        for path in sorted((root / "tests").rglob("*.py")):
            frozen[path.relative_to(root).as_posix()] = sha(path)
        environment = dict(os.environ, DSH_HOST_ROOT=str(args.host_root.resolve()))
        command = [sys.executable, "-m", "pytest", "tests", "-q", "--durations=10", "--junitxml=" + str(output / "pytest.xml")]
        receipt["command"] = command
        with (output / "pytest.log").open("wb") as log:
            result = subprocess.run(command, cwd=str(root), env=environment, stdout=log, stderr=log)
        receipt["exit_code"] = result.returncode
        receipt["junit_sha256"] = sha(output / "pytest.xml")
        if result.returncode:
            raise ValueError("Plugin regression failed; see pytest.log")
        if sha(archive) != receipt["plugin_sha256"] or any(sha(root / name) != expected for name, expected in frozen.items()):
            raise ValueError("Candidate or test source changed during regression")
        receipt["sources"] = frozen
        receipt["passed"] = True
    finally:
        receipt["wall_seconds"] = round(time.monotonic() - started, 3)
        (output / "regression.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--host-root", type=Path, default=Path(__file__).resolve().parents[3])
    run(parser.parse_args())
