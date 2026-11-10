"""Explicit scaffold failures; never report a successful parse."""


class MinerUError(RuntimeError):
    code = "MINERU_ERROR"


class NotConfigured(MinerUError):
    code = "NOT_CONFIGURED"


class PendingImplementation(MinerUError):
    code = "NOT_IMPLEMENTED"


class ServiceClosed(MinerUError):
    code = "SERVICE_CLOSED"
