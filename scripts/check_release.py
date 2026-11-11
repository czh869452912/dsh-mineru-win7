"""Check evidence for one exact plugin ZIP; offline success never implies stable readiness."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
import zipfile


def sha(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            value.update(block)
    return value.hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def portable(path, identity, bits, win7=False):
    receipt = load(path)
    if receipt.get("passed") is not True or receipt.get("plugin_sha256") != identity or not receipt.get("portable_sha256"):
        raise ValueError("Portable receipt failed or belongs to another ZIP")
    phases = receipt.get("phases", [])
    if [row.get("phase") for row in phases] != ["fresh", "cold", "removed"]:
        raise ValueError("Portable phases incomplete")
    for row in phases:
        if row.get("passed") is not True or row.get("bitness") != bits:
            raise ValueError("Portable runtime bitness or phase failed")
        if win7 and (row.get("platform") != "win32" or
                row.get("windows_version", "").split(".")[:3] != ["6", "1", "7601"]):
            raise ValueError("Win7 SP1 evidence requires an actual Windows 6.1.7601 runtime")
        if row["phase"] != "fresh" and row.get("requests") != 0:
            raise ValueError("Cold/uninstall unexpectedly used remote HTTP")
        browser = load(path.parent / row["phase"] / "browser.json")
        if browser.get("passed") is not True or browser.get("phase") != row["phase"] or browser.get("errors"):
            raise ValueError("Browser evidence missing or failed")
    return dict(path=str(path), sha256=sha(path), portable_sha256=receipt["portable_sha256"])


def evaluate(archive, junit, lanes, live=None, win7=None):
    identity = sha(archive)
    with zipfile.ZipFile(str(archive)) as source:
        manifest = json.loads(source.read("package.json"))
        names = source.namelist()
        if len(names) != len(set(names)) or set(names) != set(manifest["dsh"]["release"]["files"]):
            raise ValueError("ZIP inventory does not match manifest")
        for name, expected in manifest["dsh"]["webArtifacts"]["files"].items():
            if hashlib.sha256(source.read(name)).hexdigest() != expected:
                raise ValueError("Web artifact hash mismatch")
    tree = ET.parse(str(junit))
    cases = list(tree.iter("testcase"))
    if not cases or any(case.find(tag) is not None for case in cases for tag in ("failure", "error", "skipped")):
        raise ValueError("Regression XML contains failures/skips or no executed cases")
    regression = load(junit.parent / "regression.json")
    if (regression.get("plugin_sha256") != identity or regression.get("passed") is not True or
            regression.get("junit_sha256") != sha(junit) or regression.get("scope") != "all-plugin-tests"):
        raise ValueError("Regression identity or scope mismatch")
    evidence = dict(regression=dict(path=str(junit), sha256=sha(junit), cases=len(cases)))
    for bits in (32, 64):
        evidence[str(bits)] = portable(lanes[bits], identity, bits)
    blockers = []
    if live is None:
        blockers.append("Real MinerU protocol and text recognition evidence missing")
    else:
        receipt = load(live)
        checks = receipt.get("quality_checks", [])
        expected = {(name, fmt) for name in ("probe.pdf", "probe.png", "probe.docx") for fmt in ("zip", "json")}
        host = urlsplit(receipt.get("base_url", "")).hostname
        if (receipt.get("passed") is not True or receipt.get("plugin_sha256") != identity or
                not receipt.get("server_identity") or receipt["server_identity"] == "unverified" or
                host in (None, "localhost", "127.0.0.1", "::1") or
                {(row.get("source"), row.get("format")) for row in checks} != expected or
                len(checks) != 6 or any(row.get("passed") is not True for row in checks)):
            raise ValueError("Real service quality evidence incomplete or mismatched")
        evidence["live"] = dict(path=str(live), sha256=sha(live))
    if win7 is None:
        blockers.append("Win7 SP1 browser/runtime evidence missing")
    else:
        win_bits = load(win7).get("phases", [{}])[0].get("bitness")
        if win_bits not in (32, 64):
            raise ValueError("Invalid Win7 bitness")
        evidence["win7"] = portable(win7, identity, win_bits, win7=True)
    if "-" in manifest["version"]:
        blockers.append("Package version is a prerelease; stable version not selected")
    return dict(kind="plugin-release-check", plugin_sha256=identity, version=manifest["version"],
        offline_qualified=True, stable_ready=not blockers, blockers=blockers, evidence=evidence,
        limitation="Checks recorded evidence, not independent server image attestation; not a host Portable release gate.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "junit", "x86", "x64", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--live", type=Path)
    parser.add_argument("--win7", type=Path)
    parser.add_argument("--require-stable", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    try:
        result = evaluate(args.archive, args.junit, {32: args.x86, 64: args.x64}, args.live, args.win7)
        (args.output / "release.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Offline qualified; stable ready: " + str(result["stable_ready"]))
        for blocker in result["blockers"]:
            print("Pending: " + blocker)
        sys.exit(2 if args.require_stable and not result["stable_ready"] else 0)
    except (ValueError, KeyError, OSError, ET.ParseError, zipfile.BadZipFile) as error:
        (args.output / "failure.json").write_text(json.dumps(dict(passed=False, error=str(error))), encoding="utf-8")
        raise SystemExit("Release check failed: " + str(error))
