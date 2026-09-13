#!/usr/bin/env python3
"""Run authentication integration checks against isolated PostgreSQL and Redis."""

from __future__ import annotations

import argparse
import base64
import os
import secrets
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
INTEGRATION_TEST = "services/auth-service/tests/test_auth_integration.py"


class AuthenticationCheckFailure(RuntimeError):
    """A safe-to-display authentication integration failure."""


def redact(output: str, values: tuple[str, ...]) -> str:
    redacted = output
    for value in sorted((value for value in values if value), key=len, reverse=True):
        redacted = redacted.replace(value, "<redacted>")
    return redacted


@dataclass(frozen=True, slots=True)
class ComposeProject:
    project_name: str
    compose_files: tuple[str, ...]

    def command(self, *arguments: str) -> list[str]:
        command = [
            "docker",
            "compose",
            "--env-file",
            ".env",
            "-p",
            self.project_name,
        ]
        for compose_file in self.compose_files:
            command.extend(("-f", compose_file))
        command.extend(("--profile", "infrastructure", *arguments))
        return command

    def capture(self, *arguments: str) -> str:
        result = subprocess.run(
            self.command(*arguments),
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise AuthenticationCheckFailure("Docker Compose command failed")
        return result.stdout.strip()


def container_value(project: ComposeProject, service: str, key: str) -> str:
    value = project.capture("exec", "-T", service, "printenv", key)
    if not value:
        raise AuthenticationCheckFailure(f"{service} is missing required configuration")
    return value


def published_port(project: ComposeProject, service: str, container_port: str) -> str:
    published = project.capture("port", service, container_port)
    if ":" not in published:
        raise AuthenticationCheckFailure(f"{service} loopback port was not published")
    return published.rsplit(":", 1)[1]


def connection_urls(project: ComposeProject) -> tuple[str, str, tuple[str, ...]]:
    postgres_user = container_value(project, "postgres", "POSTGRES_USER")
    postgres_password = container_value(project, "postgres", "POSTGRES_PASSWORD")
    postgres_database = container_value(project, "postgres", "POSTGRES_DB")
    redis_password = container_value(project, "redis", "REDIS_PASSWORD")
    postgres_port = published_port(project, "postgres", "5432")
    redis_port = published_port(project, "redis", "6379")
    database_url = (
        f"postgresql+psycopg://{quote(postgres_user, safe='')}:"
        f"{quote(postgres_password, safe='')}@127.0.0.1:{postgres_port}/"
        f"{quote(postgres_database, safe='')}"
    )
    redis_url = f"redis://:{quote(redis_password, safe='')}@127.0.0.1:{redis_port}/0"
    return (
        database_url,
        redis_url,
        (
            database_url,
            redis_url,
            postgres_password,
            redis_password,
        ),
    )


def ephemeral_authentication_environment() -> tuple[dict[str, str], tuple[str, ...]]:
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
    private_b64 = base64.b64encode(private_bytes).decode()
    public_b64 = base64.b64encode(public_bytes).decode()
    hmac_secret = secrets.token_urlsafe(48)
    test_password = secrets.token_urlsafe(24)
    values = {
        "AUTH_JWT_PRIVATE_KEY_B64": private_b64,
        "AUTH_JWT_PUBLIC_KEY_B64": public_b64,
        "AUTH_JWT_ISSUER": "trialscribe-auth-test",
        "AUTH_JWT_AUDIENCE": "trialscribe-api-test",
        "AUTH_ACCESS_TOKEN_TTL_SECONDS": "900",
        "AUTH_REFRESH_TOKEN_TTL_SECONDS": "2592000",
        "AUTH_COOKIE_SECURE": "false",
        "AUTH_HMAC_SECRET": hmac_secret,
        "AUTH_LOGIN_ATTEMPT_LIMIT": "5",
        "AUTH_LOGIN_WINDOW_SECONDS": "300",
        "TRIALSCRIBE_AUTH_INTEGRATION": "1",
        "TRIALSCRIBE_AUTH_TEST_PASSWORD": test_password,
    }
    return values, (private_b64, public_b64, hmac_secret, test_password)


def run_command(
    command: list[str],
    environment: dict[str, str],
    redactions: tuple[str, ...],
    failure_message: str,
) -> None:
    result = subprocess.run(
        command,
        cwd=BACKEND_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    output = redact(result.stdout + result.stderr, redactions).strip()
    if result.returncode != 0:
        raise AuthenticationCheckFailure(output or failure_message)
    if output:
        print(output)


def migrate(environment: dict[str, str], redactions: tuple[str, ...]) -> None:
    run_command(
        [
            "uv",
            "run",
            "--frozen",
            "--package",
            "trialscribe-database",
            "alembic",
            "-c",
            "packages/database/alembic.ini",
            "upgrade",
            "head",
        ],
        environment,
        redactions,
        "Authentication migrations failed",
    )


def run_phase(
    phase: str,
    state_file: Path,
    environment: dict[str, str],
    redactions: tuple[str, ...],
) -> None:
    phase_environment = environment.copy()
    phase_environment.update(
        TRIALSCRIBE_AUTH_PHASE=phase,
        TRIALSCRIBE_AUTH_STATE_FILE=str(state_file),
    )
    run_command(
        [
            "uv",
            "run",
            "--frozen",
            "--package",
            "trialscribe-auth",
            "pytest",
            INTEGRATION_TEST,
            "-q",
        ],
        phase_environment,
        redactions,
        f"Authentication {phase} phase failed",
    )


def run_checks(project: ComposeProject) -> None:
    database_url, redis_url, connection_redactions = connection_urls(project)
    auth_environment, auth_redactions = ephemeral_authentication_environment()
    environment = os.environ.copy()
    environment.update(auth_environment, DATABASE_URL=database_url, REDIS_URL=redis_url)
    redactions = (*connection_redactions, *auth_redactions)

    with tempfile.TemporaryDirectory(prefix="trialscribe-auth-test-") as temp_dir:
        state_file = Path(temp_dir) / "session-state.json"
        migrate(environment, redactions)
        run_phase("prepare", state_file, environment, redactions)
        project.capture("restart", "postgres", "redis")
        project.capture(
            "up",
            "-d",
            "--wait",
            "--wait-timeout",
            "120",
            "postgres",
            "redis",
        )
        database_url, redis_url, restarted_redactions = connection_urls(project)
        environment.update(DATABASE_URL=database_url, REDIS_URL=redis_url)
        redactions = (*redactions, *restarted_redactions)
        run_phase("verify", state_file, environment, redactions)

    remaining = project.capture("ps", "--status", "exited", "--quiet")
    if remaining:
        raise AuthenticationCheckFailure("Authentication left an exited test container")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--compose-file", action="append", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project = ComposeProject(args.project_name, tuple(args.compose_file))
    try:
        run_checks(project)
    except AuthenticationCheckFailure as error:
        print(f"Authentication checks failed: {error}", file=sys.stderr)
        return 1
    print("Authentication account, token, throttle, restart, and cleanup checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
