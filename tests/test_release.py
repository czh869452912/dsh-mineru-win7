import importlib.util
import json
from pathlib import Path
import zipfile

import pytest


@pytest.fixture
def evidence(tmp_path):
    path = Path(__file__).resolve().parents[1] / "scripts/check_release.py"
    spec = importlib.util.spec_from_file_location("release_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    archive = tmp_path / "plugin.zip"
    manifest = dict(version="0.1.0-rc.1", dsh=dict(release=dict(files=["package.json"]), webArtifacts=dict(files={})))
    with zipfile.ZipFile(str(archive), "w") as stream:
        stream.writestr("package.json", json.dumps(manifest))
    identity = module.sha(archive)
    junit = tmp_path / "pytest.xml"
    junit.write_text('<testsuite><testcase name="one"/></testsuite>', encoding="utf-8")
    (tmp_path / "regression.json").write_text(json.dumps(dict(passed=True, scope="all-plugin-tests",
        plugin_sha256=identity, junit_sha256=module.sha(junit))), encoding="utf-8")
    lanes = {}
    for bits in (32, 64):
        root = tmp_path / str(bits)
        root.mkdir()
        phases = []
        for phase in ("fresh", "cold", "removed"):
            directory = root / phase
            directory.mkdir()
            (directory / "browser.json").write_text(json.dumps(dict(passed=True, phase=phase, errors=[])), encoding="utf-8")
            phases.append(dict(phase=phase, passed=True, bitness=bits, requests=1 if phase == "fresh" else 0,
                platform="win32", windows_version="10.0.1"))
        lanes[bits] = root / "receipt.json"
        lanes[bits].write_text(json.dumps(dict(passed=True, plugin_sha256=identity, portable_sha256="fixture", phases=phases)), encoding="utf-8")
    return module, archive, junit, lanes


def test_offline_evidence_never_certifies_stable(evidence):
    module, archive, junit, lanes = evidence
    result = module.evaluate(archive, junit, lanes)
    assert result["offline_qualified"] and not result["stable_ready"]
    assert len(result["blockers"]) == 3


@pytest.mark.parametrize("damage", ["hash", "bits", "phase", "browser", "regression", "skipped", "fake-win7", "win7-rtm"])
def test_gate_rejects_mismatched_or_incomplete_evidence(evidence, damage):
    module, archive, junit, lanes = evidence
    row = module.load(lanes[32])
    if damage == "hash": row["plugin_sha256"] = "another"
    if damage == "bits": row["phases"][0]["bitness"] = 64
    if damage == "phase": row["phases"].pop()
    if damage == "win7-rtm":
        for phase in row["phases"]:
            phase["windows_version"] = "6.1.7600"
    lanes[32].write_text(json.dumps(row), encoding="utf-8")
    if damage == "browser": (lanes[32].parent / "cold/browser.json").unlink()
    if damage == "regression": (junit.parent / "regression.json").write_text("{}", encoding="utf-8")
    if damage == "skipped": junit.write_text('<testsuite><testcase><skipped/></testcase></testsuite>', encoding="utf-8")
    with pytest.raises((ValueError, OSError)):
        module.evaluate(archive, junit, lanes, win7=lanes[32] if damage in ("fake-win7", "win7-rtm") else None)


@pytest.mark.parametrize("damage", [None, "quality", "loopback", "identity"])
def test_stable_requires_complete_matching_external_evidence(evidence, damage):
    # Synthetic receipts exercise the checker; they are never acceptance evidence.
    module, archive, junit, lanes = evidence
    with zipfile.ZipFile(str(archive)) as stream:
        manifest = json.loads(stream.read("package.json"))
    manifest["version"] = "0.1.0"
    with zipfile.ZipFile(str(archive), "w") as stream:
        stream.writestr("package.json", json.dumps(manifest))
    identity = module.sha(archive)
    regression = module.load(junit.parent / "regression.json")
    regression["plugin_sha256"] = identity
    (junit.parent / "regression.json").write_text(json.dumps(regression), encoding="utf-8")
    for path in lanes.values():
        row = module.load(path)
        row["plugin_sha256"] = identity
        for phase in row["phases"]:
            phase["windows_version"] = "6.1.7601"
        path.write_text(json.dumps(row), encoding="utf-8")
    live = junit.parent / "live.json"
    row = dict(passed=True, plugin_sha256=identity, server_identity="SYNTHETIC UNIT TEST",
        base_url="http://example.invalid/mineru/", quality_checks=[dict(source=name, format=fmt, passed=True)
            for name in ("probe.pdf", "probe.png", "probe.docx") for fmt in ("zip", "json")])
    if damage == "quality": row["quality_checks"][0]["passed"] = False
    if damage == "loopback": row["base_url"] = "http://127.0.0.1:18080/mineru/"
    if damage == "identity": row["plugin_sha256"] = "another"
    live.write_text(json.dumps(row), encoding="utf-8")
    if damage is None:
        assert module.evaluate(archive, junit, lanes, live=live, win7=lanes[32])["stable_ready"]
    else:
        with pytest.raises(ValueError, match="Real service quality evidence"):
            module.evaluate(archive, junit, lanes, live=live, win7=lanes[32])
