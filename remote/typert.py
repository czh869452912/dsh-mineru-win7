"""One declarative contract shared by the Python Host and original Client."""
import json
from pathlib import Path
from dsh.plugin_api import JsonSchemaCodec

TYPERT = json.loads((Path(__file__).parent / "contract.json").read_text(encoding="utf-8"))
for row in TYPERT["invocations"]:
    for item in row["parameters"] + [dict(codec=row["result"])]:
        item["codec"]["schema"] = JsonSchemaCodec(item["codec"]["schema"])
