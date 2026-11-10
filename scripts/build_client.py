"""Deterministically wrap authored plain JS for the pinned original shell."""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        stream.write(value)


def build():
    manifest = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    def codec(symbol):
        return dict(mode="strict", typeSymbol=symbol, schema=dict(type="string"))
    def parameter(name):
        return dict(name=name, wire=name, source="json", codec=codec("dsh-mineru-win7#Text"))
    def invocation(method, params):
        return dict(id="dsh-mineru-win7#mineruPanel." + method, service="mineruPanel", namespace="mineruPanel",
                    method=method, invocation=dict(kind="direct"), parameters=params, result=codec("dsh-mineru-win7#Text"))
    run = invocation("run", [dict(name="agent", wire="agentId", source="lookup", lookup="agent",
        codec=codec("@deepseek-ai/dsh-session/types#SessionId")), parameter("operation"), parameter("arguments")])
    run["cancellation"] = dict(parameter="signal")
    contract = dict(package=manifest["name"], face="host", schemas=[], model=dict(services=[], events=[], objects=[]),
                    invocations=[invocation("info", []), run])
    text = json.dumps(contract, ensure_ascii=True, indent=2) + "\n"
    write(ROOT / "remote/contract.json", text)
    source = (ROOT / "src/client.js").read_text(encoding="utf-8")
    bundle = ('window.__ModuleLoader__.load({id: ' + json.dumps(manifest["name"]) + ', factory: function(require) {\n'
              'var module = {exports: {}}; var exports = module.exports;\nvar React = require("react");\n'
              'var CONTRACT = ' + text.strip() + ';\n' + source + '\nreturn module.exports;\n}});\n'
              '//# sourceMappingURL=client.js.map\n')
    write(ROOT / "client/client.js", bundle)
    write(ROOT / "client/client.js.map", json.dumps(dict(version=3, sources=["../src/client.js"],
        sourcesContent=[source], names=[], mappings=""), ensure_ascii=True) + "\n")
    host = Path(os.environ.get("DSH_HOST_ROOT", str(ROOT.parents[1])))
    baseline = json.loads((host / "migration/baseline.json").read_text(encoding="utf-8"))
    paths = ("client/client.js", "client/client.js.map", "remote/contract.json", "remote/typert.py")
    manifest["exports"] = {"./client": "./client/client.js", "./typert": "./remote/typert.py"}
    manifest["dsh"]["client"] = dict(platform="web", inject=[], external=["react"])
    manifest["dsh"]["webArtifacts"] = dict(formatVersion=1, targetUpstream=baseline["target_upstream"],
        files={path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths})
    files = manifest["dsh"]["release"]["files"]
    for path in paths + ("src/client.js", "python/mineru_win7/web.py"):
        if path not in files:
            files.append(path)
    write(ROOT / "package.json", json.dumps(manifest, ensure_ascii=True, indent=2) + "\n")


if __name__ == "__main__":
    build()
