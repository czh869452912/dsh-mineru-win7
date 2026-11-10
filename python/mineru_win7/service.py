"""Business-service boundary; permissions, ownership and storage come next."""

from typing import Any, Dict

from .providers.base import MinerUProvider


class MinerUService:
    def __init__(self, provider: MinerUProvider):
        self.provider = provider

    async def health(self) -> Dict[str, Any]:
        return await self.provider.health()

    async def submit(self, file_path: str) -> Dict[str, Any]:
        return await self.provider.submit(file_path)

    async def status(self, task_id: str) -> Dict[str, Any]:
        return await self.provider.status(task_id)

    async def result(self, task_id: str) -> Dict[str, Any]:
        return await self.provider.result(task_id)

    def close(self) -> None:
        self.provider.close()
