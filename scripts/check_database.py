#!/usr/bin/env python3
"""Run PostgreSQL integration checks against an isolated Compose project."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
INTEGRATION_TEST = "packages/database/tests/test_postgres_integration.py"


class DatabaseCheckFailure(RuntimeError):
    """A safe-to-display database check failure."""


def redact(output: str, values: tuple[str, ...]) -> str:
    """Remove credentials and connection URLs from command output."""

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
            raise DatabaseCheckFailure("Docker Compose command failed")
        return result.stdout.strip()


def container_value(project: ComposeProject, key: str) -> str:
    value = project.capture("exec", "-T", "postgres", "printenv", key)
    if not value:
        raise DatabaseCheckFailure(f"PostgreSQL container is missing {key}")
    return value


def database_url(project: ComposeProject) -> tuple[str, tuple[str, ...]]:
    published = project.capture("port", "postgres", "5432")
    if ":" not in published:
        raise DatabaseCheckFailure("PostgreSQL loopback port was not published")
    port = published.rsplit(":", 1)[1]
    username = container_value(project, "POSTGRES_USER")
    password = container_value(project, "POSTGRES_PASSWORD")
    database = container_value(project, "POSTGRES_DB")
    url = (
        f"postgresql+psycopg://{quote(username, safe='')}:{quote(password, safe='')}"
        f"@127.0.0.1:{port}/{quote(database, safe='')}"
    )
    return url, (url, username, password)


def run_integration_phase(phase: str, url: str, redactions: tuple[str, ...]) -> None:
    environment = os.environ.copy()
    environment.update(
        DATABASE_URL=url,
        TRIALSCRIBE_DATABASE_INTEGRATION="1",
        TRIALSCRIBE_DATABASE_PHASE=phase,
    )
    result = subprocess.run(
        ["uv", "run", "pytest", INTEGRATION_TEST, "-q"],
        cwd=BACKEND_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    output = redact(result.stdout + result.stderr, redactions)
    if result.returncode != 0:
        raise DatabaseCheckFailure(output.strip() or f"Database {phase} phase failed")
    if output.strip():
        print(output.strip())


def run_checks(project: ComposeProject) -> None:
    url, redactions = database_url(project)
    run_integration_phase("prepare", url, redactions)
    project.capture("restart", "postgres")
    project.capture("up", "-d", "--wait", "--wait-timeout", "120", "postgres")
    restarted_url, restarted_redactions = database_url(project)
    run_integration_phase(
        "verify",
        restarted_url,
        (*redactions, *restarted_redactions),
    )
    remaining = project.capture("ps", "--status", "exited", "--quiet")
    if remaining:
        raise DatabaseCheckFailure("PostgreSQL left an exited test container")


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
    except DatabaseCheckFailure as error:
        print(f"Database checks failed: {error}", file=sys.stderr)
        return 1
    print("Database migration, transaction, vector, and restart checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
