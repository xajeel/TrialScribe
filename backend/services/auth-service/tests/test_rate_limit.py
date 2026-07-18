import base64
import secrets
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from trialscribe_auth.config import AuthSettings
from trialscribe_auth.security.rate_limit import (
    LoginRateLimiter,
    RateLimitUnavailableError,
)


def auth_settings() -> AuthSettings:
    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return AuthSettings(
        auth_jwt_private_key_b64=base64.b64encode(private_bytes).decode(),
        auth_jwt_public_key_b64=base64.b64encode(public_bytes).decode(),
        auth_jwt_issuer="trialscribe-auth",
        auth_jwt_audience="trialscribe-api",
        auth_access_token_ttl_seconds=900,
        auth_refresh_token_ttl_seconds=2_592_000,
        auth_cookie_secure=False,
        auth_hmac_secret=secrets.token_urlsafe(32),
        auth_login_attempt_limit=5,
        auth_login_window_seconds=300,
        redis_url="redis://:private-password@localhost:6379/0",
    )


class FakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.ttls: dict[str, int] = {}
        self.calls: list[tuple[str, int, tuple[Any, ...]]] = []
        self.fail = False

    async def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: Any,
    ) -> list[int]:
        if self.fail:
            raise ConnectionError("redis://:secret@internal:6379/0")
        self.calls.append((script, numkeys, keys_and_args))
        key = str(keys_and_args[0])
        window = int(keys_and_args[1])
        self.counts[key] = self.counts.get(key, 0) + 1
        self.ttls.setdefault(key, window)
        return [self.counts[key], self.ttls[key]]

    async def delete(self, *names: str) -> int:
        if self.fail:
            raise ConnectionError("redis://:secret@internal:6379/0")
        removed = 0
        for name in names:
            removed += int(name in self.counts)
            self.counts.pop(name, None)
            self.ttls.pop(name, None)
        return removed

    def expire_window(self) -> None:
        self.counts.clear()
        self.ttls.clear()


@pytest.mark.anyio
async def test_first_five_failures_pass_and_sixth_is_throttled() -> None:
    backend = FakeRedis()
    limiter = LoginRateLimiter(backend, auth_settings())

    first_five = [
        await limiter.record_failure("person@example.com", "192.0.2.10")
        for _ in range(5)
    ]
    sixth = await limiter.record_failure("person@example.com", "192.0.2.10")

    assert all(decision.allowed for decision in first_five)
    assert sixth.allowed is False
    assert sixth.retry_after == 300


@pytest.mark.anyio
async def test_window_expiry_resets_the_failure_count() -> None:
    backend = FakeRedis()
    limiter = LoginRateLimiter(backend, auth_settings())
    for _ in range(6):
        await limiter.record_failure("person@example.com", "192.0.2.10")

    backend.expire_window()

    assert (
        await limiter.record_failure("person@example.com", "192.0.2.10")
    ).allowed


@pytest.mark.anyio
async def test_success_clears_only_the_matching_email_and_peer_key() -> None:
    backend = FakeRedis()
    limiter = LoginRateLimiter(backend, auth_settings())
    await limiter.record_failure("person@example.com", "192.0.2.10")
    await limiter.record_failure("person@example.com", "192.0.2.11")

    await limiter.clear_success("person@example.com", "192.0.2.10")

    assert len(backend.counts) == 1
    remaining_key = next(iter(backend.counts))
    assert "192.0.2" not in remaining_key
    assert "person@example.com" not in remaining_key


@pytest.mark.anyio
async def test_redis_keys_never_contain_email_or_peer_address() -> None:
    backend = FakeRedis()
    limiter = LoginRateLimiter(backend, auth_settings())

    await limiter.record_failure("private.person@example.com", "203.0.113.25")

    _, numkeys, arguments = backend.calls[0]
    key = str(arguments[0])
    assert numkeys == 1
    assert key.startswith("trialscribe:auth:login:")
    assert "private.person@example.com" not in key
    assert "203.0.113.25" not in key


@pytest.mark.anyio
async def test_counter_and_expiry_are_one_atomic_script_call() -> None:
    backend = FakeRedis()
    limiter = LoginRateLimiter(backend, auth_settings())

    await limiter.record_failure("person@example.com", "192.0.2.10")

    script, _, arguments = backend.calls[0]
    assert "redis.call('INCR'" in script
    assert "redis.call('EXPIRE'" in script
    assert "redis.call('TTL'" in script
    assert arguments[1] == 300


@pytest.mark.anyio
async def test_redis_failure_is_safe_and_fail_closed() -> None:
    backend = FakeRedis()
    backend.fail = True
    limiter = LoginRateLimiter(backend, auth_settings())

    with pytest.raises(RateLimitUnavailableError) as captured:
        await limiter.record_failure("person@example.com", "192.0.2.10")

    assert str(captured.value) == "Authentication service unavailable"
    assert "redis" not in str(captured.value).casefold()
    assert "secret" not in str(captured.value).casefold()
