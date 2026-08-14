#!/usr/bin/env python3
"""Run AI-runtime checks against isolated PostgreSQL, Redis, Kafka, and Chroma."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
INTEGRATION_TESTS = (
    "services/worker-service/tests/test_ai_runtime_integration.py",
    "services/worker-service/tests/test_rag_integration.py",
    "services/worker-service/tests/test_web_research_integration.py",
)
COORDINATOR_PROBE_GROUP = "trialscribe-ai-runtime-coordinator-readiness"
COORDINATOR_ATTEMPTS = 30
COORDINATOR_RETRY_SECONDS = 2.0


class AIRuntimeCheckFailure(RuntimeError):
    """A safe-to-display AI-runtime integration failure."""


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
            raise AIRuntimeCheckFailure("Docker Compose command failed")
        return result.stdout.strip()

    def succeeds(self, *arguments: str) -> bool:
        result = subprocess.run(
            self.command(*arguments),
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0


def container_value(project: ComposeProject, service: str, key: str) -> str:
    value = project.capture("exec", "-T", service, "printenv", key)
    if not value:
        raise AIRuntimeCheckFailure(f"{service} is missing required configuration")
    return value


def published_port(project: ComposeProject, service: str, container_port: str) -> str:
    published = project.capture("port", service, container_port)
    if ":" not in published:
        raise AIRuntimeCheckFailure(f"{service} loopback port was not published")
    return published.rsplit(":", 1)[1]


def database_connection(project: ComposeProject) -> tuple[str, tuple[str, ...]]:
    user = container_value(project, "postgres", "POSTGRES_USER")
    password = container_value(project, "postgres", "POSTGRES_PASSWORD")
    database = container_value(project, "postgres", "POSTGRES_DB")
    port = published_port(project, "postgres", "5432")
    url = (
        f"postgresql+psycopg://{quote(user, safe='')}:"
        f"{quote(password, safe='')}@127.0.0.1:{port}/{quote(database, safe='')}"
    )
    return url, (url, password)


def redis_connection(project: ComposeProject) -> tuple[str, tuple[str, ...]]:
    password = container_value(project, "redis", "REDIS_PASSWORD")
    port = published_port(project, "redis", "6379")
    url = f"redis://:{quote(password, safe='')}@127.0.0.1:{port}/0"
    return url, (url, password)


def broker_address(project: ComposeProject) -> str:
    return f"127.0.0.1:{published_port(project, 'kafka', '9092')}"


def chroma_url(project: ComposeProject) -> str:
    return f"http://127.0.0.1:{published_port(project, 'chroma', '8000')}"


def wait_for_group_coordinator(project: ComposeProject) -> None:
    """Block until consumer groups work on a freshly started broker (bug B24)."""

    for _ in range(COORDINATOR_ATTEMPTS):
        if project.succeeds(
            "exec",
            "-T",
            "kafka",
            "/opt/kafka/bin/kafka-consumer-groups.sh",
            "--bootstrap-server",
            "localhost:29092",
            "--group",
            COORDINATOR_PROBE_GROUP,
            "--describe",
        ):
            return
        time.sleep(COORDINATOR_RETRY_SECONDS)
    raise AIRuntimeCheckFailure("Kafka group coordinator did not become available")


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
        raise AIRuntimeCheckFailure(output or failure_message)
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
            "0013_evidence_chunks",
        ],
        environment,
        redactions,
        "AI runtime migrations failed",
    )


def run_integration_tests(environment: dict[str, str], redactions: tuple[str, ...]) -> None:
    run_command(
        [
            "uv",
            "run",
            "--frozen",
            "--package",
            "trialscribe-worker",
            "pytest",
            *INTEGRATION_TESTS,
            "-q",
        ],
        environment,
        redactions,
        "AI runtime integration tests failed",
    )


def run_checks(project: ComposeProject) -> None:
    wait_for_group_coordinator(project)
    database_url, database_redactions = database_connection(project)
    redis_url, redis_redactions = redis_connection(project)
    redactions = database_redactions + redis_redactions
    environment = os.environ.copy()
    environment.update(
        DATABASE_URL=database_url,
        REDIS_URL=redis_url,
        EVENTS_BOOTSTRAP_SERVERS=broker_address(project),
        CHROMA_URL=chroma_url(project),
        TRIALSCRIBE_AI_RUNTIME_INTEGRATION="1",
        WORKER_CHAT_PROVIDER="fake",
        WORKER_EMBEDDING_PROVIDER="fake",
        COMPOSE_PROJECT_NAME=project.project_name,
        TRIALSCRIBE_COMPOSE_FILES=",".join(project.compose_files),
    )

    migrate(environment, redactions)
    run_integration_tests(environment, redactions)

    remaining = project.capture("ps", "--status", "exited", "--quiet")
    if remaining:
        raise AIRuntimeCheckFailure("AI runtime checks left an exited container")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--compose-file", action="append", required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    project = ComposeProject(
        project_name=arguments.project_name,
        compose_files=tuple(arguments.compose_file),
    )
    try:
        run_checks(project)
    except AIRuntimeCheckFailure as failure:
        print(str(failure), file=sys.stderr)
        return 1
    print(
        "healthy ai runtime provider probe, metering, isolation, chroma durability, "
        "and fixture retrieval"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
