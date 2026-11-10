"""Bounded legacy JSON / ZIP extraction into an unpublished owned directory."""
import asyncio
import base64
import binascii
import os
import stat
import struct
import zipfile
from pathlib import Path

from .http import ResponseError
from .storage import safe_name, digest_file
from .transport import check_cancel


class ArtifactBuilder:
    def __init__(self, root, config, budget, signal):
        self.root, self.config, self.signal = Path(root), config, signal
        self.maximum = min(budget, config.max_extract_bytes)
        self.used, self.files, self.names = 0, [], set()

    async def write(self, name, stream):
        safe_name(name)
        folded = name.casefold()
        if folded in self.names or len(self.files) >= self.config.max_files:
            raise ResponseError("Duplicate artifact or too many artifact files.")
        self.names.add(folded)
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as output:
            while True:
                check_cancel(self.signal)
                block = stream.read(65536)
                if not block:
                    break
                self.used += len(block)
                if self.used > self.maximum:
                    raise ResponseError("Extracted artifacts exceed their storage budget.")
                output.write(block)
                await asyncio.sleep(0)
        self.files.append(dict(name=name, size=path.stat().st_size, sha256=digest_file(path)))

    async def zip(self, source):
        # Reject excessive central-directory counts before ZipFile allocates entries.
        source.seek(0, os.SEEK_END)
        size = source.tell()
        source.seek(max(0, size - 65557))
        tail = source.read()
        index = tail.rfind(b"PK\x05\x06")
        if index < 0 or len(tail) - index < 22:
            raise ResponseError("ZIP end-of-directory is missing.")
        signature, disk, central_disk, count_disk, count, central_size, central_offset, comment = struct.unpack(
            "<4s4H2LH", tail[index:index + 22])
        if (disk or central_disk or count != count_disk or count > self.config.max_files or
                count == 65535 or central_size > self.config.max_files * 4096 or
                len(tail) - index != 22 + comment or central_offset + central_size > size):
            raise ResponseError("Unsupported multi-disk/ZIP64 or oversized ZIP directory.")
        source.seek(0)
        try:
            with zipfile.ZipFile(source) as archive:
                entries = archive.infolist()
                if len(entries) != count:
                    raise ResponseError("ZIP directory count mismatch.")
                seen, total = set(), 0
                for entry in entries:
                    # ZipInfo normalizes backslashes on Windows and truncates
                    # embedded NULs. Validate the original wire name first.
                    raw_name = entry.orig_filename
                    safe_name(raw_name[:-1] if raw_name.endswith("/") else raw_name)
                    if raw_name != entry.filename:
                        raise ResponseError("ZIP filename changes under Windows normalization.")
                    name = entry.filename[:-1] if entry.is_dir() else entry.filename
                    safe_name(name)
                    folded = name.casefold()
                    kind = stat.S_IFMT(entry.external_attr >> 16)
                    if (folded in seen or entry.flag_bits & 1 or
                            kind not in (0, stat.S_IFREG, stat.S_IFDIR) or
                            entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) or
                            entry.file_size > max(1, entry.compress_size) * 1000):
                        raise ResponseError("Unsafe or unsupported ZIP entry.")
                    seen.add(folded)
                    total += entry.file_size
                    if total > self.maximum:
                        raise ResponseError("ZIP expands beyond its storage budget.")
                for entry in entries:
                    check_cancel(self.signal)
                    if not entry.is_dir():
                        with archive.open(entry) as stream:
                            await self.write(entry.filename, stream)
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError, OSError) as error:
            raise ResponseError("ZIP extraction failed (%s)." % type(error).__name__) from None
        return []

    async def json(self, response):
        import io
        payload = response.json(self.config.max_json_bytes)
        results = payload.get("results")
        if not isinstance(results, dict) or not results or len(results) > self.config.max_files:
            raise ResponseError("Result JSON must contain nonempty results.")
        response.body.seek(0)
        await self.write("result.json", response.body)
        mapping = []
        for index, (remote_name, item) in enumerate(results.items(), 1):
            if not isinstance(item, dict):
                raise ResponseError("Invalid per-document result.")
            folder = "document-%d" % index
            mapping.append(dict(remote_name=remote_name, directory=folder))
            if "md_content" in item:
                if not isinstance(item["md_content"], str):
                    raise ResponseError("md_content must be a string.")
                await self.write(folder + "/document.md", io.BytesIO(item["md_content"].encode("utf-8")))
            images = item.get("images", {})
            if not isinstance(images, dict):
                raise ResponseError("images must be an object.")
            for name, data in images.items():
                safe_name(name)
                if "/" in name or not isinstance(data, str):
                    raise ResponseError("Invalid image result.")
                header, separator, encoded = data.partition(",")
                if not separator or not header.startswith("data:image/") or not header.endswith(";base64"):
                    raise ResponseError("Image result must be an inline base64 image.")
                try:
                    raw = base64.b64decode(encoded, validate=True)
                except (ValueError, binascii.Error):
                    raise ResponseError("Invalid base64 image.") from None
                await self.write(folder + "/images/" + name, io.BytesIO(raw))
        return mapping
