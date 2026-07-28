#!/usr/bin/env python3
"""Run conversation workspace integration checks against isolated PostgreSQL."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
INTEGRATION_TESTS = (
    "services/ai-engine/tests/test_conversation_integration.py",
    "services/ai-engine/tests/test_m11_section_integration.py",
)


class ConversationCheckFailure(RuntimeError):
    """A safe-to-display conversation integration failure."""


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
            raise ConversationCheckFailure("Docker Compose command failed")
        return result.stdout.strip()


def container_value(project: ComposeProject, service: str, key: str) -> str:
    value = project.capture("exec", "-T", service, "printenv", key)
    if not value:
        raise ConversationCheckFailure(f"{service} is missing required configuration")
    return value


def database_connection(project: ComposeProject) -> tuple[str, tuple[str, ...]]:
    user = container_value(project, "postgres", "POSTGRES_USER")
    password = container_value(project, "postgres", "POSTGRES_PASSWORD")
    database = container_value(project, "postgres", "POSTGRES_DB")
    published = project.capture("port", "postgres", "5432")
    if ":" not in published:
        raise ConversationCheckFailure("PostgreSQL loopback port was not published")
    port = published.rsplit(":", 1)[1]
    url = (
        f"postgresql+psycopg://{quote(user, safe='')}:"
        f"{quote(password, safe='')}@127.0.0.1:{port}/{quote(database, safe='')}"
    )
    return url, (url, password)


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
        raise ConversationCheckFailure(output or failure_message)
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
        "Conversation migrations failed",
    )


def run_phase(
    phase: str,
    conversation_state_file: Path,
    m11_state_file: Path,
    environment: dict[str, str],
    redactions: tuple[str, ...],
) -> None:
    phase_environment = environment.copy()
    phase_environment.update(
        TRIALSCRIBE_AI_CONVERSATION_INTEGRATION="1",
        TRIALSCRIBE_AI_CONVERSATION_PHASE=phase,
        TRIALSCRIBE_AI_CONVERSATION_STATE_FILE=str(conversation_state_file),
        TRIALSCRIBE_AI_M11_INTEGRATION="1",
        TRIALSCRIBE_AI_M11_PHASE=phase,
        TRIALSCRIBE_AI_M11_STATE_FILE=str(m11_state_file),
    )
    run_command(
        [
            "uv",
            "run",
            "--frozen",
            "--package",
            "trialscribe-ai",
            "pytest",
            *INTEGRATION_TESTS,
            "-q",
        ],
        phase_environment,
        redactions,
        f"Conversation {phase} phase failed",
    )


def run_checks(project: ComposeProject) -> None:
    database_url, redactions = database_connection(project)
    environment = os.environ.copy()
    environment.update(DATABASE_URL=database_url)

    with tempfile.TemporaryDirectory(prefix="trialscribe-ai-test-") as temp_dir:
        conversation_state_file = Path(temp_dir) / "conversation-state.json"
        m11_state_file = Path(temp_dir) / "m11-state.json"
        migrate(environment, redactions)
        run_phase(
            "prepare",
            conversation_state_file,
            m11_state_file,
            environment,
            redactions,
        )
        project.capture("restart", "postgres")
        project.capture("up", "-d", "--wait", "--wait-timeout", "120", "postgres")
        database_url, restarted_redactions = database_connection(project)
        environment.update(DATABASE_URL=database_url)
        redactions = (*redactions, *restarted_redactions)
        run_phase(
            "verify",
            conversation_state_file,
            m11_state_file,
            environment,
            redactions,
        )

    remaining = project.capture("ps", "--status", "exited", "--quiet")
    if remaining:
        raise ConversationCheckFailure("Conversation checks left an exited test container")


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
    except ConversationCheckFailure as error:
        print(f"Conversation checks failed: {error}", file=sys.stderr)
        return 1
    print(
        "Conversation and M11 workspace isolation, history, restart, "
        "revocation, and cleanup checks passed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
