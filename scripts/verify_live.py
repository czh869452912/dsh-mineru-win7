"""Generate public probes, or opt in to a real MinerU client journey.

Never deploys a server. Uses a fresh private output directory and synthetic files.
"""
import argparse
import asyncio
import json
import os
import hashlib
import re
from pathlib import Path
import struct
import sys
import zipfile
import zlib


def probes(directory):
    text = b"BT /F1 18 Tf 40 120 Td (MinerU public integration probe) Tj ET"
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(text)).encode("ascii") + b" >>\nstream\n" + text + b"\nendstream"]
    pdf, offsets = b"%PDF-1.4\n", [0]
    for index, value in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf += ("%d 0 obj\n" % index).encode("ascii") + value + b"\nendobj\n"
    xref = len(pdf)
    pdf += b"xref\n0 6\n0000000000 65535 f \n"
    pdf += b"".join(("%010d 00000 n \n" % value).encode("ascii") for value in offsets[1:])
    pdf += ("trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % xref).encode("ascii")
    (directory / "probe.pdf").write_bytes(pdf)

    # A valid raster containing a simple visible pixel-font word, without Pillow.
    letters = {"T": [31, 4, 4, 4, 4, 4, 4], "E": [31, 16, 16, 30, 16, 16, 31],
               "S": [31, 16, 16, 31, 1, 1, 31]}
    width, height, scale = 320, 100, 8
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            col, row = (x - 25) // scale, (y - 20) // scale
            black = False
            if 0 <= row < 7 and 0 <= col < 24:
                character = "TEST"[col // 6]
                black = col % 6 < 5 and bool(letters[character][row] & (1 << (4 - col % 6)))
            rows.extend(b"\0\0\0" if black else b"\xff\xff\xff")
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(rows))) + chunk(b"IEND", b"")
    (directory / "probe.png").write_bytes(png)

    with zipfile.ZipFile(str(directory / "probe.docx"), "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        archive.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        archive.writestr("word/document.xml", '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>MinerU public Office Gateway probe</w:t></w:r></w:p></w:body></w:document>')
    return [directory / name for name in ("probe.pdf", "probe.png", "probe.docx")]


async def verify(args, output, files):
    host = Path(args.host_root).resolve()
    project = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(host))
    sys.path.insert(0, str(project / "python"))
    from dsh.cordis.context import Context
    from dsh.core.tools import ToolsService, ToolExecutionInput
    from dsh.core.agent import Agent, AgentRegistry
    from dsh.core.session import Session
    from dsh.core.system_prompt.service import SystemPrompt
    from dsh.fs.fs_local import FsService
    from mineru_win7.plugin import MinerUPlugin
    from mineru_win7.config import MinerUConfig
    MinerUConfig.from_mapping(dict(baseURL=args.base_url), {})
    ctx = Context()
    ctx.set_service("tools", ToolsService(ctx))
    ctx.set_service("fs", FsService(cwd=str(output)))
    registry = AgentRegistry(ctx)
    ctx.set_service("agents", registry)
    await ctx.plugin(SystemPrompt)
    agent = Agent(Session("public-probe"), ctx=ctx)
    registry.register(agent)
    class Credentials:
        def resolve(self, ref):
            token = os.environ.get(args.token_env, "") if args.token_env else ""
            return {"value": token} if token else None
    ctx.set_service("credentials", Credentials())
    receipt = dict(kind="provider/client-probe", python=sys.version, base_url=args.base_url, server_identity=args.server_identity,
                   limitation="Operator-supplied server identity; not an independently verified image digest.", steps=[], quality_checks=[])
    if getattr(args, "plugin_archive", ""):
        receipt["plugin_sha256"] = hashlib.sha256(Path(args.plugin_archive).read_bytes()).hexdigest()
    try:
        await ctx.plugin(MinerUPlugin, config=dict(baseURL=args.base_url, caFile=args.ca_file,
            credentialRef="MINERU_PROBE_TOKEN" if args.token_env else "", storageDirectory=str(output / "data")))
        async def call(operation, arguments):
            result = await ctx.get("tools").execute(ToolExecutionInput("probe-" + operation,
                "mineru_" + operation, arguments, agent=agent, signal=asyncio.Event()))
            value = result.value if not result.is_error else dict(ok=False, error=str(result.error))
            receipt["steps"].append(dict(operation=operation, result=value))
            (output / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
            if not value.get("ok"):
                raise RuntimeError("Probe failed: " + operation + "; see receipt.json")
            return value
        await call("health", {})
        expected = {".pdf": "MinerU public integration probe", ".png": "TEST", ".docx": "MinerU public Office Gateway probe"}
        for source in files:
            for format_ in ("zip", "json"):
                submitted = await call("submit", dict(file_path=str(source), format=format_))
                task = submitted["task"]["task_id"]
                await call("wait", dict(task_id=task, timeout_seconds=1800))
                await call("files", dict(task_id=task))
                text = await call("read", dict(task_id=task, limit=12000))
                normalize = lambda value: re.sub(r"\W+", "", value).casefold()
                passed = normalize(expected[source.suffix]) in normalize(text["text"])
                receipt["quality_checks"].append(dict(source=source.name, format=format_, passed=passed))
                if not passed:
                    raise RuntimeError("Expected probe text missing; see receipt.json")
        receipt["passed"] = True
    finally:
        await ctx.fiber.dispose()
        await ctx.fiber.await_settled()
        (output / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="Fresh output directory; must not already exist")
    parser.add_argument("--generate-only", action="store_true", help="Generate PDF, PNG and DOCX; do not connect")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--server-identity", default="unverified")
    parser.add_argument("--ca-file", default="")
    parser.add_argument("--token-env", default="", help="Name of an environment variable containing a test token")
    parser.add_argument("--plugin-archive", default="", help="ZIP whose Python source must match this checkout; binds the receipt")
    parser.add_argument("--host-root", default=os.environ.get("DSH_HOST_ROOT", str(Path(__file__).resolve().parents[3])))
    args = parser.parse_args()
    if args.plugin_archive:
        with zipfile.ZipFile(args.plugin_archive) as archive:
            project = Path(__file__).resolve().parents[1]
            for name in archive.namelist():
                if name.startswith("python/") and name.endswith(".py"):
                    if archive.read(name) != (project / name).read_bytes():
                        parser.error("Plugin ZIP source differs from this checkout: " + name)
    if not args.generate_only and not args.base_url:
        parser.error("--base-url is required unless --generate-only is used")
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    files = probes(output)
    if not args.generate_only:
        asyncio.run(verify(args, output, files))
    print("Generated probes" if args.generate_only else "Provider probe passed")


if __name__ == "__main__":
    main()
