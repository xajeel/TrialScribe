"""API-gateway enums."""

from enum import StrEnum


class ProxyTarget(StrEnum):
    AUTH = "auth"
    USER = "user"
    AI = "ai"
    WORKER = "worker"
