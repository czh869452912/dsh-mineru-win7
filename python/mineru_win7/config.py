"""Configuration and public endpoint construction; no network side effects."""

import math
import os
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional
from urllib.parse import quote, urlsplit

from .errors import NotConfigured


# Public field -> (Python field, default, lower, upper); all budgets are finite.
LIMITS = {
    "connectTimeoutSeconds": ("connect_timeout_seconds", 15, 1, 120),
    "readTimeoutSeconds": ("read_timeout_seconds", 360, 1, 3600),
    "pollIntervalSeconds": ("poll_interval_seconds", 2, 1, 60),
    "waitTimeoutSeconds": ("wait_timeout_seconds", 1800, 1, 86400),
    "maxUploadBytes": ("max_upload_bytes", 104857600, 1, 104857600),
    "maxDownloadBytes": ("max_download_bytes", 134217728, 1024, 536870912),
    "maxJsonBytes": ("max_json_bytes", 8388608, 1024, 33554432),
    "maxExtractBytes": ("max_extract_bytes", 268435456, 1024, 1073741824),
    "maxFiles": ("max_files", 2000, 1, 10000),
    "maxTasks": ("max_tasks", 1000, 1, 10000),
    "maxStorageBytes": ("max_storage_bytes", 1073741824, 1048576, 10737418240),
    "readMaxChars": ("read_max_chars", 12000, 256, 50000),
}


@dataclass(frozen=True)
class MinerUConfig:
    base_url: str = ""
    protocol: str = "legacy-tasks-v2"
    office_mode: str = "pdf_ocr"
    request_timeout_seconds: float = 360.0
    max_response_bytes: int = 65536
    connect_timeout_seconds: int = 15
    read_timeout_seconds: int = 360
    poll_interval_seconds: int = 2
    wait_timeout_seconds: int = 1800
    max_upload_bytes: int = 104857600
    max_download_bytes: int = 134217728
    max_json_bytes: int = 8388608
    max_extract_bytes: int = 268435456
    max_files: int = 2000
    max_tasks: int = 1000
    max_storage_bytes: int = 1073741824
    read_max_chars: int = 12000
    credential_ref: str = ""
    ca_file: str = ""
    storage_directory: str = ""
    enable_web_panel: bool = True

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any],
                     environ: Optional[Mapping[str, str]] = None) -> "MinerUConfig":
        unknown = set(values) - ({"baseURL", "protocol", "officeMode", "requestTimeoutSeconds", "maxResponseBytes",
                                  "credentialRef", "caFile", "storageDirectory", "enableWebPanel"} | set(LIMITS))
        if unknown:
            raise ValueError("Unknown MinerU configuration fields: " + ", ".join(sorted(unknown)))
        env = os.environ if environ is None else environ
        base = values.get("baseURL", "")
        if not isinstance(base, str):
            raise ValueError("baseURL must be a string")
        base = base.strip() or env.get("MINERU_BASE_URL", "").strip()
        if base:
            try:
                parsed = urlsplit(base)
                parsed.port
                valid = (parsed.scheme in ("http", "https") and parsed.hostname
                         and parsed.username is None and parsed.password is None
                         and not parsed.query and not parsed.fragment
                         and "?" not in base and "#" not in base
                         and "\\" not in base and not any(c.isspace() or ord(c) < 32 for c in base))
            except ValueError:
                valid = False
            if not valid:
                raise ValueError("baseURL must be an HTTP(S) API base without credentials, query or fragment")
            base = base.rstrip("/") + "/"
        protocol = values.get("protocol", "legacy-tasks-v2")
        if protocol != "legacy-tasks-v2":
            raise ValueError("Only legacy-tasks-v2 is supported")
        mode = values.get("officeMode", "pdf_ocr")
        if mode not in ("pdf_ocr", "native"):
            raise ValueError("officeMode must be pdf_ocr or native")
        timeout = values.get("requestTimeoutSeconds", 360)
        if (type(timeout) not in (int, float) or not 1 <= timeout <= 3600
                or not math.isfinite(timeout)):
            raise ValueError("requestTimeoutSeconds must be between 1 and 3600")
        max_bytes = values.get("maxResponseBytes", 65536)
        if type(max_bytes) is not int or not 1024 <= max_bytes <= 1048576:
            raise ValueError("maxResponseBytes must be an integer between 1024 and 1048576")
        extras = {}
        for key, (field, default, low, high) in LIMITS.items():
            value = values.get(key, default)
            if type(value) is not int or not low <= value <= high:
                raise ValueError("%s must be an integer between %s and %s" % (key, low, high))
            extras[field] = value
        for key, field in (("credentialRef", "credential_ref"), ("caFile", "ca_file"),
                           ("storageDirectory", "storage_directory")):
            value = values.get(key, "")
            if not isinstance(value, str) or any(ord(c) < 32 for c in value):
                raise ValueError(key + " must be a string without control characters")
            extras[field] = value
        if extras["credential_ref"] and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", extras["credential_ref"]):
            raise ValueError("credentialRef must name a host credential reference")
        panel = values.get("enableWebPanel", True)
        if type(panel) is not bool:
            raise ValueError("enableWebPanel must be a boolean")
        extras["enable_web_panel"] = panel
        return cls(base, protocol, mode, float(timeout), max_bytes, **extras)

    def endpoint(self, operation: str, task_id: Optional[str] = None) -> str:
        if not self.base_url:
            raise NotConfigured("Set baseURL or MINERU_BASE_URL to your public MinerU API base.")
        if operation == "health":
            return self.base_url + "health"
        if operation == "submit":
            return self.base_url + "tasks"
        if operation not in ("status", "result"):
            raise ValueError("Unknown MinerU operation")
        if (not isinstance(task_id, str) or not task_id or task_id in (".", "..")
                or any(ord(c) < 32 for c in task_id)):
            raise ValueError("A valid task_id is required")
        suffix = "tasks/" + quote(task_id, safe="")
        return self.base_url + suffix + ("/result" if operation == "result" else "")
