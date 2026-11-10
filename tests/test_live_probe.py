"""Exercise the opt-in probe against the local protocol fixture, never a GPU server."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile
from xml.etree import ElementTree


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
    args = SimpleNamespace(host_root=str(Path(__file__).resolve().parents[3]),
        base_url=task_server["base"], server_identity="LOCAL PROTOCOL FIXTURE ONLY", ca_file="", token_env="")
    await module.verify(args, tmp_path, files)
    receipt = json.loads((tmp_path / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["passed"] and len(receipt["steps"]) == 13
    assert sum(row[0] == "POST" for row in task_server["requests"]) == 3
