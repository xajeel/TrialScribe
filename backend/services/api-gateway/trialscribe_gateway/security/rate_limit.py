"""In-process fixed-window request throttling for the public gateway."""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from collections.abc import Callable
from dataclasses import dataclass

from trialscribe_gateway.config import GatewaySettings
from trialscribe_gateway.utils.constant import (
    RATE_LIMIT_FAMILY_AUTH,
    RATE_LIMIT_MAX_KEYS,
)


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int | None = None


class GatewayRateLimiter:
    """Count requests per hashed caller and route family for one process."""

    def __init__(
        self,
        settings: GatewaySettings,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._monotonic = monotonic
        self._api_limit = settings.gateway_rate_limit_requests
        self._auth_limit = settings.gateway_rate_limit_auth_requests
        self._window_seconds = settings.gateway_rate_limit_window_seconds
        secret = settings.gateway_rate_limit_hmac_secret
        self._hmac_key = secret.encode() if secret is not None else os.urandom(32)
        self._windows: dict[str, tuple[int, int]] = {}

    def check(self, host: str, family: str) -> RateLimitDecision:
        now = self._monotonic()
        window_id = int(now // self._window_seconds)
        key = self._key(family, host)
        current = self._windows.get(key)
        if current is None or current[0] != window_id:
            self._evict(window_id)
            if key not in self._windows and len(self._windows) >= RATE_LIMIT_MAX_KEYS:
                self._windows.pop(next(iter(self._windows)))
            count = 1
        else:
            count = current[1] + 1
        self._windows[key] = (window_id, count)
        limit = (
            self._auth_limit if family == RATE_LIMIT_FAMILY_AUTH else self._api_limit
        )
        if count <= limit:
            return RateLimitDecision(allowed=True)
        remaining = self._window_seconds - (now % self._window_seconds)
        return RateLimitDecision(allowed=False, retry_after=max(int(remaining), 1))

    def _key(self, family: str, host: str) -> str:
        message = f"{family}\0{host}".encode()
        digest = hmac.new(self._hmac_key, message, hashlib.sha256).hexdigest()
        return f"trialscribe:gateway:rl:{digest}"

    def _evict(self, window_id: int) -> None:
        expired = [
            key
            for key, (stored_window, _count) in self._windows.items()
            if stored_window != window_id
        ]
        for key in expired:
            del self._windows[key]
