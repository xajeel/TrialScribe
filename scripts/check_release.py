from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
COMMAND_TIMEOUT_SECONDS = 30.0
COMPOSE_WAIT_SECONDS = 180.0
RESTORE_WAIT_SECONDS = 180.0
OUTPUT_CHARACTER_LIMIT = 4_000
DUMP_NAME = "trialscribe-release.dump"
PROBE_TABLE = "release_restore_probe"
DEFAULT_JOB_COUNT = 10
DEFAULT_JOB_WAIT_SECONDS = 60.0
FULL_JOB_COUNT = 120
FULL_JOB_WAIT_SECONDS = 180.0
JOB_POLL_SECONDS = 1.0
HTTP_TIMEOUT_SECONDS = 10.0
K6_IMAGE = "grafana/k6:2.2.0"
K6_SCRIPT = REPO_ROOT / "infra" / "k6" / "release.js"
K6_RESULTS = REPO_ROOT / "infra" / "k6" / "results"
LOAD_COMPOSE = "infra/release/load.yml"
REGISTER_PASSWORD = "a valid research passphrase"
APP_SERVICES = ("gateway", "auth", "user", "ai", "worker", "jobs", "web")


class ReleaseCheckFailure(RuntimeError):
    """A release Compose check failed."""


def read_dotenv() -> dict[str, str]:
    values: dict[str, str] = {}
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def env_value(dotenv: dict[str, str], key: str, default: str) -> str:
    return os.environ.get(key) or dotenv.get(key) or default


def read_redactions(dotenv: dict[str, str]) -> tuple[str, ...]:
    values: list[str] = []
    for key, value in {**dotenv, **os.environ}.items():
        if key.endswith(("PASSWORD", "KEY", "TOKEN", "SECRET")) and value:
            values.append(value)
    return tuple(dict.fromkeys(values))


def redact(output: str, redactions: tuple[str, ...]) -> str:
    result = output[-OUTPUT_CHARACTER_LIMIT:]
    for value in redactions:
        if value:
            result = result.replace(value, "[redacted]")
    return result


def run_command(
    command: list[str],
    *,
    redactions: tuple[str, ...],
    timeout: float = COMMAND_TIMEOUT_SECONDS,
    input_bytes: bytes | None = None,
    text: bool = True,
) -> str | bytes:
    try:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            input=input_bytes,
            capture_output=True,
            text=text,
            timeout=timeout,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise ReleaseCheckFailure(
            f"{command[0]} timed out after {timeout:.0f} seconds"
        ) from error
    except OSError as error:
        raise ReleaseCheckFailure(f"could not run {command[0]}: {error}") from error

    if result.returncode != 0:
        output = result.stderr or result.stdout or "<no command output>"
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        raise ReleaseCheckFailure(
            f"{' '.join(command[:6])} exited with status {result.returncode}\n"
            f"{redact(output, redactions)}"
        )
    if text:
        return str(result.stdout).strip()
    return result.stdout


@dataclass(frozen=True)
class ComposeProject:
    name: str
    files: tuple[str, ...]
    profiles: tuple[str, ...]
    redactions: tuple[str, ...]

    def command(self, *arguments: str) -> list[str]:
        command = ["docker", "compose", "--env-file", ".env", "-p", self.name]
        for compose_file in self.files:
            command.extend(["-f", compose_file])
        for profile in self.profiles:
            command.extend(["--profile", profile])
        command.extend(arguments)
        return command

    def run(
        self,
        *arguments: str,
        timeout: float = COMMAND_TIMEOUT_SECONDS,
    ) -> str:
        output = run_command(
            self.command(*arguments),
            redactions=self.redactions,
            timeout=timeout,
        )
        return str(output)

    def exec(self, service: str, *arguments: str) -> str:
        return self.run("exec", "-T", service, *arguments)

    def exec_bytes(
        self,
        service: str,
        *arguments: str,
        input_bytes: bytes | None = None,
        timeout: float = COMMAND_TIMEOUT_SECONDS,
    ) -> bytes:
        output = run_command(
            self.command("exec", "-T", service, *arguments),
            redactions=self.redactions,
            timeout=timeout,
            input_bytes=input_bytes,
            text=False,
        )
        assert isinstance(output, bytes)
        return output


def postgres_sql(project: ComposeProject, sql: str) -> str:
    return project.exec(
        "postgres",
        "sh",
        "-c",
        'exec psql -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" '
        '-d "$POSTGRES_DB" -c "$1"',
        "trialscribe-release-check",
        sql,
    )


def dump_path(dotenv: dict[str, str]) -> Path:
    directory = REPO_ROOT / env_value(dotenv, "RELEASE_BACKUP_DIR", "backups")
    directory.mkdir(parents=True, exist_ok=True)
    return directory / DUMP_NAME


def http_request(
    method: str,
    url: str,
    *,
    redactions: tuple[str, ...],
    body: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
    expected: int | None = None,
) -> tuple[int, str]:
    data = None
    request_headers = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=data, method=method, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            status = int(response.status)
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        status = int(error.code)
        payload = error.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as error:
        raise ReleaseCheckFailure(
            redact(f"{method} {url} failed: {error}", redactions)
        ) from error
    if expected is not None and status != expected:
        raise ReleaseCheckFailure(
            redact(f"{method} {url} returned {status}, expected {expected}\n{payload}", redactions)
        )
    return status, payload


def smoke(dotenv: dict[str, str], redactions: tuple[str, ...]) -> None:
    gateway = env_value(dotenv, "GATEWAY_PORT", "8000")
    web = env_value(dotenv, "RELEASE_WEB_PORT", "8080")
    for url in (
        f"http://127.0.0.1:{gateway}/health/live",
        f"http://127.0.0.1:{gateway}/health/ready",
        f"http://127.0.0.1:{web}/",
    ):
        http_request("GET", url, redactions=redactions, expected=200)
    print("healthy release smoke")


def backup(project: ComposeProject, dotenv: dict[str, str]) -> Path:
    target = dump_path(dotenv)
    payload = project.exec_bytes(
        "postgres",
        "sh",
        "-c",
        'exec pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"',
        timeout=120.0,
    )
    target.write_bytes(payload)
    print("healthy release backup")
    return target


def stop_apps(project: ComposeProject) -> None:
    project.run("stop", *APP_SERVICES, timeout=COMPOSE_WAIT_SECONDS)


def start_apps(project: ComposeProject) -> None:
    project.run(
        "up",
        "-d",
        "--wait",
        "--wait-timeout",
        "180",
        *APP_SERVICES,
        timeout=RESTORE_WAIT_SECONDS,
    )


def restore_dump(project: ComposeProject, target: Path) -> None:
    if not target.is_file():
        raise ReleaseCheckFailure(f"backup file is missing: {target.name}")
    stop_apps(project)
    postgres_sql(
        project,
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE pid <> pg_backend_pid() AND datname = current_database();",
    )
    try:
        project.exec_bytes(
            "postgres",
            "sh",
            "-c",
            'exec pg_restore --clean --if-exists --no-owner '
            '-U "$POSTGRES_USER" -d "$POSTGRES_DB"',
            input_bytes=target.read_bytes(),
            timeout=120.0,
        )
    finally:
        start_apps(project)


def restore(project: ComposeProject, dotenv: dict[str, str]) -> None:
    restore_dump(project, dump_path(dotenv))
    print("healthy release restore")


def restore_rehearsal(project: ComposeProject, dotenv: dict[str, str]) -> None:
    postgres_sql(
        project,
        f"DROP TABLE IF EXISTS {PROBE_TABLE}; "
        f"CREATE TABLE {PROBE_TABLE} (id int PRIMARY KEY, note text); "
        f"INSERT INTO {PROBE_TABLE} VALUES (1, 'before-backup');",
    )
    target = backup(project, dotenv)
    postgres_sql(project, f"DELETE FROM {PROBE_TABLE};")
    restore_dump(project, target)
    note = postgres_sql(project, f"SELECT note FROM {PROBE_TABLE} WHERE id = 1;")
    postgres_sql(project, f"DROP TABLE IF EXISTS {PROBE_TABLE};")
    if note.strip() != "before-backup":
        raise ReleaseCheckFailure("restored probe row was missing")
    print("healthy release restore")


def restart(project: ComposeProject, dotenv: dict[str, str], redactions: tuple[str, ...]) -> None:
    project.run("restart", "gateway", timeout=COMPOSE_WAIT_SECONDS)
    project.run(
        "up",
        "-d",
        "--wait",
        "--wait-timeout",
        "120",
        "gateway",
        timeout=COMPOSE_WAIT_SECONDS,
    )
    smoke(dotenv, redactions)
    print("healthy release restart")


def load_full(dotenv: dict[str, str]) -> bool:
    return env_value(dotenv, "RELEASE_LOAD_FULL", "0") in {"1", "true", "TRUE", "yes"}


def enqueue_probe_jobs(
    dotenv: dict[str, str],
    redactions: tuple[str, ...],
) -> None:
    gateway = env_value(dotenv, "GATEWAY_PORT", "8000")
    base = f"http://127.0.0.1:{gateway}"
    email = f"release-{uuid4().hex}@example.com"
    http_request(
        "POST",
        f"{base}/v1/auth/register",
        redactions=redactions,
        body={"email": email, "password": REGISTER_PASSWORD},
        expected=201,
    )
    _, login_payload = http_request(
        "POST",
        f"{base}/v1/auth/login",
        redactions=redactions,
        body={"email": email, "password": REGISTER_PASSWORD},
        expected=200,
    )
    token = json.loads(login_payload)["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}
    _, org_payload = http_request(
        "POST",
        f"{base}/v1/organizations",
        redactions=redactions,
        body={"name": "release-probe"},
        headers=auth_headers,
        expected=201,
    )
    organization_id = json.loads(org_payload)["id"]
    job_headers = {
        **auth_headers,
        "X-Organization-ID": organization_id,
    }
    count = FULL_JOB_COUNT if load_full(dotenv) else DEFAULT_JOB_COUNT
    wait_seconds = FULL_JOB_WAIT_SECONDS if load_full(dotenv) else DEFAULT_JOB_WAIT_SECONDS
    job_ids: list[str] = []
    for _ in range(count):
        _, created = http_request(
            "POST",
            f"{base}/v1/jobs",
            redactions=redactions,
            body={"kind": "probe"},
            headers=job_headers,
            expected=202,
        )
        job_ids.append(json.loads(created)["id"])
    deadline = time.monotonic() + wait_seconds
    pending = set(job_ids)
    while pending and time.monotonic() < deadline:
        finished: list[str] = []
        for job_id in pending:
            _, body = http_request(
                "GET",
                f"{base}/v1/jobs/{job_id}",
                redactions=redactions,
                headers=job_headers,
                expected=200,
            )
            status = json.loads(body)["status"]
            if status == "succeeded":
                finished.append(job_id)
            elif status in {"failed", "cancelled"}:
                raise ReleaseCheckFailure(f"probe job ended as {status}")
        pending.difference_update(finished)
        if pending:
            time.sleep(JOB_POLL_SECONDS)
    if pending:
        raise ReleaseCheckFailure(f"{len(pending)} probe jobs did not succeed in time")
    print("healthy release jobs")


def load_compose(project: ComposeProject) -> ComposeProject:
    if LOAD_COMPOSE in project.files:
        return project
    return ComposeProject(
        name=project.name,
        files=(*project.files, LOAD_COMPOSE),
        profiles=project.profiles,
        redactions=project.redactions,
    )


def recreate_gateway(project: ComposeProject) -> None:
    project.run(
        "up",
        "-d",
        "--no-deps",
        "--wait",
        "--wait-timeout",
        "120",
        "gateway",
        timeout=COMPOSE_WAIT_SECONDS,
    )


def run_k6(dotenv: dict[str, str], redactions: tuple[str, ...]) -> None:
    K6_RESULTS.mkdir(parents=True, exist_ok=True)
    K6_RESULTS.chmod(0o777)
    full = load_full(dotenv)
    vus = "500" if full else env_value(dotenv, "K6_VUS", "20")
    duration = "2m" if full else env_value(dotenv, "K6_DURATION", "30s")
    p95_ms = env_value(dotenv, "K6_P95_MS", "500" if full else "2000")
    gateway = env_value(dotenv, "GATEWAY_PORT", "8000")
    summary = K6_RESULTS / "last-summary.json"
    timeout = 360.0 if full else 180.0
    run_command(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "host",
            "-e",
            f"BASE_URL=http://127.0.0.1:{gateway}",
            "-e",
            f"K6_VUS={vus}",
            "-e",
            f"K6_DURATION={duration}",
            "-e",
            f"K6_P95_MS={p95_ms}",
            "-v",
            f"{K6_SCRIPT}:/scripts/release.js:ro",
            "-v",
            f"{K6_RESULTS}:/results",
            K6_IMAGE,
            "run",
            "--summary-export",
            "/results/last-summary.json",
            "/scripts/release.js",
        ],
        redactions=redactions,
        timeout=timeout,
    )
    if not summary.is_file():
        raise ReleaseCheckFailure("k6 summary was not written")


def run_load(
    project: ComposeProject,
    dotenv: dict[str, str],
    redactions: tuple[str, ...],
    *,
    revert_limits: bool,
) -> None:
    loaded = load_compose(project)
    recreate_gateway(loaded)
    try:
        run_k6(dotenv, redactions)
    finally:
        if revert_limits:
            recreate_gateway(project)
    print("healthy release load")


def run_test(
    project: ComposeProject,
    dotenv: dict[str, str],
    redactions: tuple[str, ...],
) -> None:
    smoke(dotenv, redactions)
    restore_rehearsal(project, dotenv)
    restart(project, dotenv, redactions)
    enqueue_probe_jobs(dotenv, redactions)
    run_load(project, dotenv, redactions, revert_limits=False)
    print("healthy release test")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check the Compose release stack")
    parser.add_argument("--project-name", default="trialscribe-release")
    parser.add_argument("--compose-file", action="append", dest="compose_files")
    parser.add_argument(
        "--action",
        required=True,
        choices=("smoke", "backup", "restore", "restart", "jobs", "load", "test"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dotenv = read_dotenv()
    redactions = read_redactions(dotenv)
    project = ComposeProject(
        name=args.project_name,
        files=tuple(args.compose_files or ["docker-compose.yml", "infra/release/compose.yml"]),
        profiles=("infrastructure", "release"),
        redactions=redactions,
    )
    try:
        if args.action == "smoke":
            smoke(dotenv, redactions)
        elif args.action == "backup":
            backup(project, dotenv)
        elif args.action == "restore":
            restore(project, dotenv)
        elif args.action == "restart":
            restart(project, dotenv, redactions)
        elif args.action == "jobs":
            enqueue_probe_jobs(dotenv, redactions)
        elif args.action == "load":
            run_load(project, dotenv, redactions, revert_limits=True)
        else:
            run_test(project, dotenv, redactions)
    except ReleaseCheckFailure as error:
        print(f"release check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
