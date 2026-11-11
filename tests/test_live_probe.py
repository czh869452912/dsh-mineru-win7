"""Exercise the opt-in probe against the local protocol fixture, never a GPU server."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile
from xml.etree import ElementTree

import pytest


async def test_generated_probes_complete_local_script_journey(tmp_path, task_server):
    spec = importlib.util.spec_from_file_location("mineru_verify_live", Path(__file__).resolve().parents[1] / "scripts/verify_live.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    files = module.probes(tmp_path)
    assert files[0].read_bytes().startswith(b"%PDF-1.4")
    assert files[1].read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    with zipfile.ZipFile(str(files[2])) as archive:
        for name in archive.namelist():
            ElementTree.fromstring(archive.read(name))
    task_server["status"] = "completed"
    task_server["result_body"] = json.dumps({"results": {"probe": {"md_content": "MinerU public integration probe TEST MinerU public Office Gateway probe"}}}).encode("utf-8")
    args = SimpleNamespace(host_root=str(Path(__file__).resolve().parents[3]),
        base_url=task_server["base"], server_identity="LOCAL PROTOCOL FIXTURE ONLY", ca_file="", token_env="")
    await module.verify(args, tmp_path, files)
    receipt = json.loads((tmp_path / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["passed"] and len(receipt["steps"]) == 25
    assert len(receipt["quality_checks"]) == 6
    assert sum(row[0] == "POST" for row in task_server["requests"]) == 6


async def test_probe_rejects_completed_task_with_wrong_recognition(tmp_path, task_server):
    spec = importlib.util.spec_from_file_location("mineru_verify_live_wrong", Path(__file__).resolve().parents[1] / "scripts/verify_live.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    files = module.probes(tmp_path)
    task_server["status"] = "completed"
    task_server["result_body"] = json.dumps({"results": {"probe": {"md_content": "Unrelated recognized text"}}}).encode("utf-8")
    args = SimpleNamespace(host_root=str(Path(__file__).resolve().parents[3]),
        base_url=task_server["base"], server_identity="LOCAL PROTOCOL FIXTURE ONLY", ca_file="", token_env="")
    with pytest.raises(RuntimeError, match="Expected probe text missing"):
        await module.verify(args, tmp_path, files)
    receipt = json.loads((tmp_path / "receipt.json").read_text(encoding="utf-8"))
    assert not receipt.get("passed")
    assert receipt["quality_checks"] == [dict(source="probe.pdf", format="zip", passed=False)]
    assert sum(row[0] == "POST" for row in task_server["requests"]) == 1
