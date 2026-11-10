"""Cordis entry point for the opt-in Python plugin package."""

from dsh.plugin_api import Plugin, Schema

from .config import MinerUConfig
from .providers.legacy_tasks import LegacyTasksProvider
from .service import MinerUService
from .tools import register_tools


class MinerUPlugin(Plugin):
    id = "mineru-win7"
    name = "dsh-mineru-win7"
    inject = ["tools"]
    Config = Schema.object({
        "baseURL": Schema.string().default(""),
        "protocol": Schema.const_("legacy-tasks-v2").default("legacy-tasks-v2"),
        "officeMode": Schema.union([Schema.const_("pdf_ocr"), Schema.const_("native")]).default("pdf_ocr"),
        "requestTimeoutSeconds": Schema.number().min(1).max(3600).default(360),
    })

    def apply(self, ctx, config):
        resolved = MinerUConfig.from_mapping(config)
        service = MinerUService(LegacyTasksProvider(resolved))
        ctx.set_service("mineruWin7", service)
        ctx.effect(lambda: service.close)
        register_tools(ctx)
