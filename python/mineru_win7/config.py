"""Configuration and public endpoint construction; no network side effects."""

import math
import os
from dataclasses import dataclass
from typing import Any, Mapping, Optional
from urllib.parse import quote, urlsplit

from .errors import NotConfigured


@dataclass(frozen=True)
class MinerUConfig:
    base_url: str = ""
    protocol: str = "legacy-tasks-v2"
    office_mode: str = "pdf_ocr"
    request_timeout_seconds: float = 360.0

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any],
                     environ: Optional[Mapping[str, str]] = None) -> "MinerUConfig":
        unknown = set(values) - {"baseURL", "protocol", "officeMode", "requestTimeoutSeconds"}
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
            raise ValueError("Only legacy-tasks-v2 is scaffolded")
        mode = values.get("officeMode", "pdf_ocr")
        if mode not in ("pdf_ocr", "native"):
            raise ValueError("officeMode must be pdf_ocr or native")
        timeout = values.get("requestTimeoutSeconds", 360)
        if (type(timeout) not in (int, float) or not 1 <= timeout <= 3600
                or not math.isfinite(timeout)):
            raise ValueError("requestTimeoutSeconds must be between 1 and 3600")
        return cls(base, protocol, mode, float(timeout))

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
