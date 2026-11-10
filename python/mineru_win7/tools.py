"""Thin tool adapters; the service owns permissions, tasks and artifacts."""
import json
from .errors import MinerUError


STRING = {"type": "string"}
INTEGER = {"type": "integer"}
BOOLEAN = {"type": "boolean"}
TASK = {"task_id": STRING}
DEFINITIONS = {
    "health": ({}, [], "Probe the configured public MinerU health endpoint; ok means HTTP/JSON success, not component readiness."),
    "submit": ({"file_path": STRING, "office_mode": STRING, "backend": STRING, "parse_method": STRING,
                "language": STRING, "format": STRING, "images": BOOLEAN}, ["file_path"],
               "Upload one authorized PDF, image or Office file. Returns a LOCAL owner-bound task_id. Do not automatically retry submission-unknown outcomes."),
    "status": (TASK, ["task_id"], "Query a task submitted by this Agent/session using its local task_id."),
    "result": (TASK, ["task_id"], "Download and safely save bounded JSON/ZIP artifacts for an owned task; returns a manifest, not full document text."),
    "list": ({"offset": INTEGER, "limit": INTEGER}, [], "List this Agent/session's local tasks. Paginated, offset defaults to 0, limit to 20 (maximum 100)."),
    "files": ({**TASK, "offset": INTEGER, "limit": INTEGER}, ["task_id"],
              "List an owned task's artifact manifest in bounded pages. offset defaults to 0, limit to 20 (maximum 100)."),
    "read": ({**TASK, "artifact": STRING, "offset": INTEGER, "limit": INTEGER}, ["task_id"],
             "Read a UTF-8 artifact in bounded character windows. offset is zero-based characters; use next_offset to continue. Defaults to the first Markdown artifact."),
    "wait": ({**TASK, "background": BOOLEAN, "download": BOOLEAN, "timeout_seconds": INTEGER}, ["task_id"],
             "Poll an owned task to completion and optionally download results. background uses host jobs; job_kill stops LOCAL waiting and does not cancel the remote task."),
    "forget": (TASK, ["task_id"], "Forget an owned local task and delete only unchanged manifest artifacts. Does not delete or cancel the remote task."),
}

OUTPUT_SCHEMA = {"type": "object", "additionalProperties": False, "properties": {
    "ok": BOOLEAN, "code": STRING, "message": STRING, "healthFormat": STRING,
    "data": {"type": "object"}, "task": {"type": "object"},
    "tasks": {"type": "array", "items": {"type": "object"}},
    "files": {"type": "array", "items": {"type": "object"}},
    "task_id": STRING, "job_id": STRING, "artifact": STRING, "text": STRING,
    "offset": INTEGER, "next_offset": INTEGER, "eof": BOOLEAN,
}, "required": ["ok", "code", "message"]}


def register_tools(ctx):
    for operation, (properties, required, description) in DEFINITIONS.items():
        async def execute(args, execution, operation=operation, required=required):
            for key in required:
                if not args[key].strip():
                    return dict(ok=False, code="INVALID_ARGUMENT", message=key + " must not be empty.")
            try:
                return await ctx.get("mineruWin7").execute(operation, args, execution)
            except MinerUError as error:
                result = dict(ok=False, code=error.code, message=str(error))
                if hasattr(error, "task_id"):
                    result["task_id"] = error.task_id
                return result
            except (OSError, UnicodeError) as error:
                return dict(ok=False, code="LOCAL_IO_ERROR", message="Local artifact operation failed (%s)." % type(error).__name__)

        disposer = ctx.get("tools").register(dict(name="mineru_" + operation, description=description,
            parameters={"type": "object", "additionalProperties": False, "properties": properties, "required": required},
            execute=execute, output={"schema": OUTPUT_SCHEMA,
            "render": lambda args, value: [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]}))
        ctx.effect(lambda disposer=disposer: disposer)
