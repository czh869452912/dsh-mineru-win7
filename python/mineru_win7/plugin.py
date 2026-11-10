"""Cordis entry point for the opt-in Python plugin package."""

from dsh.plugin_api import Plugin, Schema

from .config import MinerUConfig, LIMITS
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
        "maxResponseBytes": Schema.number().min(1024).max(1048576).default(65536),
        "credentialRef": Schema.string().default(""),
        "caFile": Schema.string().default(""),
        "storageDirectory": Schema.string().default(""),
        "enableWebPanel": Schema.boolean().default(True),
        **{key: Schema.number().min(low).max(high).default(default)
           for key, (field, default, low, high) in LIMITS.items()},
    })

    def apply(self, ctx, config):
        resolved = MinerUConfig.from_mapping(config)
        def credential():
            if not resolved.credential_ref:
                return ""
            from .errors import MinerUError
            credentials = ctx.get("credentials")
            value = credentials.resolve(resolved.credential_ref) if credentials is not None else None
            if value is None:
                raise MinerUError("Configured MinerU credential reference is unavailable.")
            return value["value"]
        service = MinerUService(LegacyTasksProvider(resolved, credential), ctx)
        ctx.set_service("mineruWin7", service)
        ctx.effect(lambda: service.close)
        register_tools(ctx)
        from .web import MinerUWebService
        MinerUWebService(ctx, resolved)
