"""Optional original-shell Remote face: calls always traverse host tools policy."""
import json
import uuid

from dsh.plugin_api import Remote, TypertRemoteService, ToolExecutionInput
from .tools import DEFINITIONS


class MinerUWebService(TypertRemoteService):
    def __init__(self, ctx, config):
        super().__init__(ctx, "mineruPanel")
        self.config = config

    @Remote
    async def info(self):
        agents = self.ctx.get("agents")
        return json.dumps(dict(enabled=self.config.enable_web_panel,
            baseURL=self.config.base_url, protocol=self.config.protocol, officeMode=self.config.office_mode,
            credentialRef=self.config.credential_ref, caConfigured=bool(self.config.ca_file),
            agents=[dict(id=a.id, title=a.session.header.get("title", a.id))
                    for a in agents.list()] if agents is not None else []), ensure_ascii=False)

    @Remote
    async def run(self, agent, operation, arguments, signal):
        if not self.config.enable_web_panel:
            raise ValueError("MinerU Web panel is disabled")
        if operation not in set(DEFINITIONS) | {"job_kill", "job_output"} or len(arguments) > 16384:
            raise ValueError("Invalid MinerU panel operation")
        args = json.loads(arguments)
        if not isinstance(args, dict):
            raise ValueError("Tool arguments must be an object")
        # Use the initiating Agent's tool service, preserving scoped policy layers.
        tools = agent.ctx.get("tools")
        tool = operation if operation.startswith("job_") else "mineru_" + operation
        result = await tools.execute(ToolExecutionInput(uuid.uuid4().hex, tool,
                                                      args, agent=agent, signal=signal))
        value = result.value if not result.is_error else dict(ok=False, code="TOOL_ERROR",
                                                              message=result.content[0].get("text", "Tool failed"))
        return json.dumps(value, ensure_ascii=False)
