"""Structured client failures exposed through the host tool contract."""


class MinerUError(RuntimeError):
    code = "MINERU_ERROR"


class NotConfigured(MinerUError):
    code = "NOT_CONFIGURED"


class ServiceClosed(MinerUError):
    code = "SERVICE_CLOSED"
