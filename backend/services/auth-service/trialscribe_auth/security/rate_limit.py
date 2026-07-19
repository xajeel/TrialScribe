"""Privacy-preserving Redis login throttling."""

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any, Protocol

from trialscribe_auth.config import AuthSettings
from trialscribe_auth.utils.constant import FIXED_WINDOW_SCRIPT
from trialscribe_auth.utils.exceptions import RateLimitUnavailableError


class AsyncRateLimitBackend(Protocol):
    async def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: Any,
    ) -> Any: ...

    async def delete(self, *names: str) -> int: ...


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int | None = None


class LoginRateLimiter:
    """Share failed-login windows across service instances through Redis."""

    def __init__(
        self,
        backend: AsyncRateLimitBackend,
        settings: AuthSettings,
    ) -> None:
        self._backend = backend
        self._hmac_key = settings.hmac_key()
        self._attempt_limit = settings.auth_login_attempt_limit
        self._window_seconds = settings.auth_login_window_seconds

    def _key(self, normalized_email: str, peer_address: str) -> str:
        message = f"login:{peer_address}\0{normalized_email}".encode()
        digest = hmac.new(self._hmac_key, message, hashlib.sha256).hexdigest()
        return f"trialscribe:auth:login:{digest}"

    async def record_failure(
        self,
        normalized_email: str,
        peer_address: str,
    ) -> RateLimitDecision:
        key = self._key(normalized_email, peer_address)
        try:
            raw_result = await self._backend.eval(
                FIXED_WINDOW_SCRIPT,
                1,
                key,
                self._window_seconds,
            )
            count, ttl = int(raw_result[0]), int(raw_result[1])
        except Exception:
            raise RateLimitUnavailableError(
                "Authentication service unavailable"
            ) from None

        if count <= self._attempt_limit:
            return RateLimitDecision(allowed=True)
        return RateLimitDecision(allowed=False, retry_after=max(ttl, 1))

    async def clear_success(
        self,
        normalized_email: str,
        peer_address: str,
    ) -> None:
        try:
            await self._backend.delete(self._key(normalized_email, peer_address))
        except Exception:
            raise RateLimitUnavailableError(
                "Authentication service unavailable"
            ) from None
