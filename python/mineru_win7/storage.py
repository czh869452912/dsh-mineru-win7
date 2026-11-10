"""Durable owner-bound task metadata and immutable, verified result manifests."""
import hashlib
import json
import os
import re
import sqlite3
import stat
from pathlib import Path

from .errors import MinerUError


class StorageError(MinerUError):
    code = "STORAGE_ERROR"


def digest_file(path):
    digest = hashlib.sha256()
    with open(str(path), "rb") as stream:
        while True:
            block = stream.read(65536)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def no_link(path):
    info = os.lstat(str(path))
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise StorageError("Links and reparse points are not allowed in plugin storage.")
    return info


def safe_name(value):
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 240:
        raise StorageError("Invalid artifact path.")
    if "\\" in value or any(ord(c) < 32 or c in ':*?"<>|' for c in value):
        raise StorageError("Artifact path is not portable to Windows 7.")
    for part in value.split("/"):
        if (not part or part in (".", "..") or part[-1] in " ." or
                re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part)):
            raise StorageError("Unsafe artifact path.")
    return value


class TaskStore:
    def __init__(self, root, endpoint, config):
        self.root = Path(root).resolve()
        self.endpoint = hashlib.sha256(endpoint.encode("utf-8")).hexdigest()
        self.config, self.db = config, None

    def open(self):
        if self.db is not None:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        no_link(self.root)
        dbpath = self.root / "tasks.sqlite3"
        if dbpath.exists():
            no_link(dbpath)
        self.db = sqlite3.connect(str(dbpath), timeout=5)
        self.db.execute("CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, owner TEXT NOT NULL, endpoint TEXT NOT NULL, record TEXT NOT NULL)")
        self.db.commit()

    def put(self, record):
        self.open()
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO tasks VALUES (?,?,?,?)",
                            (record["task_id"], record["owner"], self.endpoint, json.dumps(record, ensure_ascii=False, allow_nan=False)))

    def get(self, task_id, owner):
        self.open()
        row = self.db.execute("SELECT record FROM tasks WHERE id=? AND owner=? AND endpoint=?",
                              (task_id, owner, self.endpoint)).fetchone()
        if row is None:
            error = StorageError("Task is unknown or belongs to a different owner or endpoint.")
            error.code = "TASK_NOT_FOUND"
            raise error
        return json.loads(row[0])

    def list(self, owner):
        self.open()
        return [json.loads(row[0]) for row in self.db.execute(
            "SELECT record FROM tasks WHERE owner=? AND endpoint=? ORDER BY rowid DESC LIMIT ?",
            (owner, self.endpoint, self.config.max_tasks))]

    def reserve(self, new_task=True):
        self.open()
        count = self.db.execute("SELECT count(*) FROM tasks").fetchone()[0]
        if new_task and count >= self.config.max_tasks:
            raise StorageError("Task budget reached; forget unneeded local tasks first.")
        used = 0
        for directory, dirs, files in os.walk(str(self.root), followlinks=False):
            no_link(directory)
            for name in dirs:
                no_link(Path(directory) / name)
            for name in files:
                used += no_link(Path(directory) / name).st_size
        return self.config.max_storage_bytes - used

    def directory(self, task_id):
        if not re.fullmatch(r"[0-9a-f]{32}", task_id):
            raise StorageError("Invalid local task ID.")
        path = self.root / task_id
        if path.exists():
            no_link(path)
        return path

    def verified_path(self, record, name):
        safe_name(name)
        artifact = next((item for item in record.get("artifacts", []) if item["name"] == name), None)
        if artifact is None:
            raise StorageError("Artifact is not present in this task manifest.")
        root = self.directory(record["task_id"])
        path = root
        for part in name.split("/"):
            path = path / part
            no_link(path)
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size != artifact["size"] or digest_file(path) != artifact["sha256"]:
            raise StorageError("Artifact content no longer matches its cache identity.")
        return path

    def forget(self, record):
        root = self.directory(record["task_id"])
        if root.exists():
            expected = {item["name"] for item in record.get("artifacts", [])}
            actual = set()
            for directory, dirs, files in os.walk(str(root), followlinks=False):
                no_link(directory)
                for name in dirs:
                    no_link(Path(directory) / name)
                for name in files:
                    path = Path(directory) / name
                    no_link(path)
                    actual.add(path.relative_to(root).as_posix())
            if actual != expected:
                raise StorageError("Unknown or missing artifact files; preserving directory for recovery.")
            paths = [self.verified_path(record, name) for name in expected]
            for path in paths:
                path.unlink()
            for directory, _, _ in os.walk(str(root), topdown=False):
                Path(directory).rmdir()
        with self.db:
            self.db.execute("DELETE FROM tasks WHERE id=? AND owner=? AND endpoint=?",
                            (record["task_id"], record["owner"], self.endpoint))

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db = None
