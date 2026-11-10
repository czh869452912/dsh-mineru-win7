"""Legacy Tasks protocol boundary; intentionally performs no I/O."""

from typing import Any, Dict, Optional

from ..config import MinerUConfig
from ..errors import PendingImplementation, ServiceClosed


class LegacyTasksProvider:
    def __init__(self, config: MinerUConfig):
        self.config = config
        self.closed = False

    def _pending(self, operation: str, task_id: Optional[str] = None) -> None:
        if self.closed:
            raise ServiceClosed("MinerU provider has been unloaded.")
        self.config.endpoint(operation, task_id)
        raise PendingImplementation("MinerU %s is scaffolded; HTTP transport is not implemented." % operation)

    async def health(self) -> Dict[str, Any]:
        self._pending("health")

    async def submit(self, file_path: str) -> Dict[str, Any]:
        # Future implementation must use host-authorized source snapshots.
        self._pending("submit")

    async def status(self, task_id: str) -> Dict[str, Any]:
        self._pending("status", task_id)

    async def result(self, task_id: str) -> Dict[str, Any]:
        self._pending("result", task_id)

    def close(self) -> None:
        self.closed = True
