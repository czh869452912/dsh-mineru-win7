"""Host filesystem snapshots: never open a model-supplied native path directly."""
import asyncio
import hashlib
import os
import tempfile
from dataclasses import dataclass

from .errors import MinerUError
from .transport import check_cancel


class FileAccessError(MinerUError):
    code = "FILE_ACCESS_ERROR"


@dataclass
class Snapshot:
    stream: object
    name: str
    size: int
    sha256: str
    source: str

    def close(self):
        self.stream.close()


async def snapshot_file(ctx, execution, path, maximum):
    source_ctx = getattr(execution.agent, "ctx", None) or ctx
    fs = source_ctx.get("fs")
    if fs is None or not hasattr(fs, "readByteRange"):
        raise FileAccessError("Host filesystem with bounded byte reads is required.")
    session = execution.agent.session
    header = session.header
    cwd = header.get("cwd") if isinstance(header, dict) else getattr(header, "cwd", None)
    options = {"signal": execution.signal}
    if cwd:
        options["cwd"] = cwd
    target = await fs.resolve(path, options)
    before = await fs.stat(target, execution.signal)
    if before is None or before.type != "file" or before.size is None:
        raise FileAccessError("Upload source must be an existing regular file.")
    if not 0 < before.size <= maximum:
        raise FileAccessError("Upload source is empty or exceeds maxUploadBytes.")
    name = os.path.basename(target.displayPath.replace("\\", "/"))
    if not name or any(ord(c) < 32 for c in name):
        raise FileAccessError("Invalid source filename.")
    stream = tempfile.TemporaryFile(mode="w+b")
    digest, offset = hashlib.sha256(), 0
    try:
        while offset < before.size:
            check_cancel(execution.signal)
            block = await fs.readByteRange(target, {"offset": offset, "length": min(65536, before.size - offset)}, execution.signal)
            if not block or len(block) > before.size - offset:
                raise FileAccessError("Source changed during snapshot.")
            stream.write(block)
            digest.update(block)
            offset += len(block)
            await asyncio.sleep(0)
        after = await fs.stat(target, execution.signal)
        if after is None or after.version != before.version or after.size != before.size:
            raise FileAccessError("Source changed during snapshot; no upload was sent.")
        check_cancel(execution.signal)
        source_ctx.emit("fs/observed", target, {"kind": "present", "version": before.version}, execution)
        stream.seek(0)
        return Snapshot(stream, name, offset, digest.hexdigest(), target.displayPath)
    except BaseException:
        stream.close()
        raise
