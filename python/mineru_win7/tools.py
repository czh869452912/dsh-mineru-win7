"""Four explicit model-facing scaffold tools with bounded error envelopes."""

import json

from .errors import MinerUError


OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "ok": {"type": "boolean"},
        "code": {"type": "string"},
        "message": {"type": "string"},
    },
    "required": ["ok", "code", "message"],
}


def register_tools(ctx):
    for operation, parameter in (("health", None), ("submit", "file_path"),
                                 ("status", "task_id"), ("result", "task_id")):
        properties = {} if parameter is None else {parameter: {"type": "string"}}

        async def execute(args, execution, operation=operation, parameter=parameter):
            if parameter is not None and not args[parameter].strip():
                return {"ok": False, "code": "INVALID_ARGUMENT", "message": parameter + " must not be empty."}
            service = ctx.get("mineruWin7")
            method = getattr(service, operation)
            try:
                return await method() if parameter is None else await method(args[parameter])
            except MinerUError as error:
                return {"ok": False, "code": error.code, "message": str(error)}

        disposer = ctx.get("tools").register({
            "name": "mineru_" + operation,
            "description": "Development scaffold for MinerU %s; returns an explicit not-implemented error and performs no I/O." % operation,
            "parameters": {"type": "object", "additionalProperties": False,
                           "properties": properties,
                           "required": [] if parameter is None else [parameter]},
            "execute": execute,
            "output": {"schema": OUTPUT_SCHEMA,
                       "render": lambda args, value: [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]},
        })
        ctx.effect(lambda disposer=disposer: disposer)
