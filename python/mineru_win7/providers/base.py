"""Provider boundary, independent of DSH and of future HTTP libraries."""

from typing import Any, Dict, Protocol


class MinerUProvider(Protocol):
    async def health(self) -> Dict[str, Any]:
        ...

    async def submit(self, file_path: str) -> Dict[str, Any]:
        ...

    async def status(self, task_id: str) -> Dict[str, Any]:
        ...

    async def result(self, task_id: str) -> Dict[str, Any]:
        ...

    def close(self) -> None:
        ...
