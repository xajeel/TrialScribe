#!/usr/bin/env python3
"""Run organization-RBAC integration checks against isolated PostgreSQL."""

from __future__ import annotations

import argparse
import base64
import os
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
INTEGRATION_TEST = "services/user-service/tests/test_organization_integration.py"


class OrganizationCheckFailure(RuntimeError):
    """A safe-to-display organization integration failure."""


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
            raise OrganizationCheckFailure("Docker Compose command failed")
        return result.stdout.strip()


def container_value(project: ComposeProject, service: str, key: str) -> str:
    value = project.capture("exec", "-T", service, "printenv", key)
    if not value:
        raise OrganizationCheckFailure(f"{service} is missing required configuration")
    return value


def database_connection(project: ComposeProject) -> tuple[str, tuple[str, ...]]:
    user = container_value(project, "postgres", "POSTGRES_USER")
    password = container_value(project, "postgres", "POSTGRES_PASSWORD")
    database = container_value(project, "postgres", "POSTGRES_DB")
    published = project.capture("port", "postgres", "5432")
    if ":" not in published:
        raise OrganizationCheckFailure("PostgreSQL loopback port was not published")
    port = published.rsplit(":", 1)[1]
    url = (
        f"postgresql+psycopg://{quote(user, safe='')}:"
        f"{quote(password, safe='')}@127.0.0.1:{port}/{quote(database, safe='')}"
    )
    return url, (url, password)


def ephemeral_environment() -> tuple[dict[str, str], tuple[str, ...]]:
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
    values = {
        "AUTH_JWT_PUBLIC_KEY_B64": public_b64,
        "AUTH_JWT_ISSUER": "trialscribe-auth-test",
        "AUTH_JWT_AUDIENCE": "trialscribe-api-test",
        "USER_INVITATION_TTL_SECONDS": "604800",
        "USER_INVITATION_ACCEPT_URL": "https://test.example/invitations/accept",
        "TRIALSCRIBE_USER_INTEGRATION": "1",
        "TRIALSCRIBE_USER_TEST_PRIVATE_KEY_B64": private_b64,
    }
    return values, (private_b64, public_b64)


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
        raise OrganizationCheckFailure(output or failure_message)
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
        "Organization migrations failed",
    )


def run_phase(
    phase: str,
    state_file: Path,
    environment: dict[str, str],
    redactions: tuple[str, ...],
) -> None:
    phase_environment = environment.copy()
    phase_environment.update(
        TRIALSCRIBE_USER_PHASE=phase,
        TRIALSCRIBE_USER_STATE_FILE=str(state_file),
    )
    run_command(
        [
            "uv",
            "run",
            "--frozen",
            "--package",
            "trialscribe-user",
            "pytest",
            INTEGRATION_TEST,
            "-q",
        ],
        phase_environment,
        redactions,
        f"Organization {phase} phase failed",
    )


def run_checks(project: ComposeProject) -> None:
    database_url, connection_redactions = database_connection(project)
    user_environment, key_redactions = ephemeral_environment()
    environment = os.environ.copy()
    environment.update(user_environment, DATABASE_URL=database_url)
    redactions = (*connection_redactions, *key_redactions)

    with tempfile.TemporaryDirectory(prefix="trialscribe-user-test-") as temp_dir:
        state_file = Path(temp_dir) / "organization-state.json"
        migrate(environment, redactions)
        run_phase("prepare", state_file, environment, redactions)
        project.capture("restart", "postgres")
        project.capture("up", "-d", "--wait", "--wait-timeout", "120", "postgres")
        database_url, restarted_redactions = database_connection(project)
        environment.update(DATABASE_URL=database_url)
        redactions = (*redactions, *restarted_redactions)
        run_phase("verify", state_file, environment, redactions)

    remaining = project.capture("ps", "--status", "exited", "--quiet")
    if remaining:
        raise OrganizationCheckFailure("Organization checks left an exited test container")


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
    except OrganizationCheckFailure as error:
        print(f"Organization checks failed: {error}", file=sys.stderr)
        return 1
    print("Organization membership, invitation, RBAC, restart, and cleanup checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
