from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
COMMAND_TIMEOUT_SECONDS = 30.0
RESTART_TIMEOUT_SECONDS = 150.0
OUTPUT_CHARACTER_LIMIT = 4_000
CLEANUP_WAIT_SECONDS = 20.0


class InfrastructureFailure(RuntimeError):
    """A local infrastructure capability failed its integration check."""


def read_redactions() -> tuple[str, ...]:
    values: list[str] = []
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip().endswith(("PASSWORD", "KEY", "TOKEN", "SECRET")):
                cleaned = value.strip().strip('"').strip("'")
                if cleaned:
                    values.append(cleaned)
    for key, value in os.environ.items():
        if key.endswith(("PASSWORD", "KEY", "TOKEN", "SECRET")) and value:
            values.append(value)
    return tuple(dict.fromkeys(values))


def redact(output: str, redactions: tuple[str, ...]) -> str:
    result = output[-OUTPUT_CHARACTER_LIMIT:]
    for value in redactions:
        result = result.replace(value, "[redacted]")
    return result


def run_command(
    command: list[str],
    *,
    redactions: tuple[str, ...],
    timeout: float = COMMAND_TIMEOUT_SECONDS,
    input_text: str | None = None,
) -> str:
    try:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise InfrastructureFailure(
            f"{command[0]} timed out after {timeout:.0f} seconds"
        ) from error
    except OSError as error:
        raise InfrastructureFailure(f"could not run {command[0]}: {error}") from error

    if result.returncode != 0:
        output = result.stderr or result.stdout or "<no command output>"
        raise InfrastructureFailure(
            f"{' '.join(command[:4])} exited with status {result.returncode}\n"
            f"{redact(output, redactions)}"
        )
    return result.stdout.strip()


@dataclass(frozen=True)
class ComposeProject:
    name: str
    files: tuple[str, ...]
    redactions: tuple[str, ...]

    def command(self, *arguments: str) -> list[str]:
        command = ["docker", "compose", "-p", self.name]
        for compose_file in self.files:
            command.extend(["-f", compose_file])
        command.extend(arguments)
        return command

    def run(
        self,
        *arguments: str,
        timeout: float = COMMAND_TIMEOUT_SECONDS,
    ) -> str:
        return run_command(
            self.command(*arguments),
            redactions=self.redactions,
            timeout=timeout,
        )

    def exec(self, service: str, *arguments: str) -> str:
        return self.run("exec", "-T", service, *arguments)


@dataclass(frozen=True)
class ProbeNames:
    token: str
    postgres_table: str
    redis_key: str
    kafka_topic: str
    chroma_collection: str

    @classmethod
    def create(cls) -> ProbeNames:
        token = uuid4().hex
        return cls(
            token=token,
            postgres_table=f"probe_{token}",
            redis_key=f"trialscribe:runtime-probe:{token}",
            kafka_topic=f"trialscribe-runtime-probe-{token}",
            chroma_collection=f"probe_{token}",
        )


def postgres_sql(project: ComposeProject, sql: str) -> str:
    return project.exec(
        "postgres",
        "sh",
        "-c",
        'exec psql -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" '
        '-d "$POSTGRES_DB" -c "$1"',
        "trialscribe-postgres-check",
        sql,
    )


def prepare_postgres(project: ComposeProject, probe: ProbeNames) -> None:
    extension = postgres_sql(
        project,
        "SELECT extname FROM pg_extension WHERE extname = 'vector';",
    )
    if extension != "vector":
        raise InfrastructureFailure("PostgreSQL vector extension is not enabled")
    postgres_sql(
        project,
        "CREATE SCHEMA IF NOT EXISTS runtime_probe; "
        f"CREATE TABLE runtime_probe.{probe.postgres_table} "
        "(token text NOT NULL, embedding vector(3) NOT NULL); "
        f"INSERT INTO runtime_probe.{probe.postgres_table} VALUES "
        f"('{probe.token}', '[1,2,3]');",
    )


def verify_postgres(project: ComposeProject, probe: ProbeNames) -> None:
    output = postgres_sql(
        project,
        f"SELECT token || '|' || (embedding <-> '[1,2,4]'::vector) "
        f"FROM runtime_probe.{probe.postgres_table};",
    )
    try:
        token, raw_distance = output.rsplit("|", 1)
        distance = float(raw_distance)
    except (ValueError, TypeError) as error:
        raise InfrastructureFailure("PostgreSQL returned an invalid vector probe") from error
    if token != probe.token or distance != 1.0:
        raise InfrastructureFailure("PostgreSQL read/write or vector distance mismatch")


def cleanup_postgres(project: ComposeProject, probe: ProbeNames) -> None:
    postgres_sql(
        project,
        f"DROP TABLE IF EXISTS runtime_probe.{probe.postgres_table};",
    )


def redis_command(project: ComposeProject, *arguments: str) -> str:
    return project.exec(
        "redis",
        "sh",
        "-c",
        'exec redis-cli --no-auth-warning -a "$REDIS_PASSWORD" "$@"',
        "trialscribe-redis-check",
        *arguments,
    )


def prepare_redis(project: ComposeProject, probe: ProbeNames) -> None:
    if redis_command(project, "SET", probe.redis_key, probe.token) != "OK":
        raise InfrastructureFailure("Redis did not acknowledge the probe write")


def verify_redis(project: ComposeProject, probe: ProbeNames) -> None:
    if redis_command(project, "GET", probe.redis_key) != probe.token:
        raise InfrastructureFailure("Redis read/write probe mismatch")


def cleanup_redis(project: ComposeProject, probe: ProbeNames) -> None:
    redis_command(project, "DEL", probe.redis_key)


def kafka_script(project: ComposeProject, script: str, *arguments: str) -> str:
    return project.exec(
        "kafka",
        f"/opt/kafka/bin/{script}",
        "--bootstrap-server",
        "localhost:29092",
        *arguments,
    )


def prepare_kafka(project: ComposeProject, probe: ProbeNames) -> None:
    kafka_script(
        project,
        "kafka-topics.sh",
        "--create",
        "--if-not-exists",
        "--topic",
        probe.kafka_topic,
        "--partitions",
        "1",
        "--replication-factor",
        "1",
    )
    project.exec(
        "kafka",
        "sh",
        "-c",
        "printf '%s\\n' \"$2\" | /opt/kafka/bin/kafka-console-producer.sh "
        "--bootstrap-server localhost:29092 --topic \"$1\"",
        "trialscribe-kafka-check",
        probe.kafka_topic,
        probe.token,
    )


def verify_kafka(project: ComposeProject, probe: ProbeNames) -> None:
    output = kafka_script(
        project,
        "kafka-console-consumer.sh",
        "--topic",
        probe.kafka_topic,
        "--from-beginning",
        "--max-messages",
        "1",
        "--timeout-ms",
        "10000",
    )
    if probe.token not in output.splitlines():
        raise InfrastructureFailure("Kafka produce/consume probe mismatch")


def cleanup_kafka(project: ComposeProject, probe: ProbeNames) -> None:
    kafka_script(
        project,
        "kafka-topics.sh",
        "--delete",
        "--if-exists",
        "--topic",
        probe.kafka_topic,
    )


CHROMA_TENANT = "default_tenant"
CHROMA_DATABASE = "default_database"
CHROMA_COLLECTIONS_PATH = (
    f"/api/v2/tenants/{CHROMA_TENANT}/databases/{CHROMA_DATABASE}/collections"
)


CHROMA_HTTP_SCRIPT = r"""
set -euo pipefail
method="$1"
path="$2"
body="${3-}"
exec 3<>/dev/tcp/127.0.0.1/8000
if [ -n "$body" ]; then
  printf '%s %s HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: %s\r\nConnection: close\r\n\r\n%s' \
    "$method" "$path" "${#body}" "$body" >&3
else
  printf '%s %s HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n' \
    "$method" "$path" >&3
fi
response=$(cat <&3 || true)
status=$(printf '%s\n' "$response" | head -n 1)
case "$status" in
  *[[:space:]]2*) ;;
  *) printf '%s\n' "$status" >&2; exit 1 ;;
esac
body_text=${response#*$'\r\n\r\n'}
printf '%s' "$body_text"
"""


def chroma_http(
    project: ComposeProject,
    method: str,
    path: str,
    payload: dict[str, object] | None = None,
) -> str:
    body = json.dumps(payload) if payload is not None else ""
    return project.exec(
        "chroma",
        "bash",
        "-c",
        CHROMA_HTTP_SCRIPT,
        "chroma-http",
        method,
        path,
        body,
    )


def chroma_json(
    project: ComposeProject,
    method: str,
    path: str,
    payload: dict[str, object] | None = None,
) -> object:
    output = chroma_http(project, method, path, payload)
    if not output:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError as error:
        raise InfrastructureFailure("Chroma returned invalid JSON") from error


def chroma_collections(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict) and isinstance(payload.get("collections"), list):
        items = payload["collections"]
    else:
        return []
    return [item for item in items if isinstance(item, dict)]


def chroma_collection_id(payload: object) -> str:
    if not isinstance(payload, dict):
        raise InfrastructureFailure("Chroma collection response was not an object")
    collection_id = payload.get("id") or payload.get("uuid")
    if not isinstance(collection_id, str) or not collection_id:
        raise InfrastructureFailure("Chroma collection response omitted id")
    return collection_id


def prepare_chroma(project: ComposeProject, probe: ProbeNames) -> None:
    heartbeat = chroma_json(project, "GET", "/api/v2/heartbeat")
    if not isinstance(heartbeat, dict) or not heartbeat:
        raise InfrastructureFailure("Chroma heartbeat did not return a payload")
    created = chroma_json(
        project,
        "POST",
        CHROMA_COLLECTIONS_PATH,
        {"name": probe.chroma_collection},
    )
    collection_id = chroma_collection_id(created)
    chroma_json(
        project,
        "POST",
        f"{CHROMA_COLLECTIONS_PATH}/{collection_id}/add",
        {
            "ids": [probe.token],
            "embeddings": [[1.0, 0.0, 0.0]],
            "documents": [probe.token],
            "metadatas": [{"token": probe.token}],
        },
    )


def verify_chroma(project: ComposeProject, probe: ProbeNames) -> None:
    collections = chroma_collections(chroma_json(project, "GET", CHROMA_COLLECTIONS_PATH))
    collection_id = None
    for collection in collections:
        if collection.get("name") == probe.chroma_collection:
            collection_id = chroma_collection_id(collection)
            break
    if collection_id is None:
        raise InfrastructureFailure("Chroma probe collection was not found")
    result = chroma_json(
        project,
        "POST",
        f"{CHROMA_COLLECTIONS_PATH}/{collection_id}/query",
        {
            "query_embeddings": [[1.0, 0.0, 0.0]],
            "n_results": 1,
            "include": ["documents", "metadatas"],
        },
    )
    encoded = json.dumps(result)
    if probe.token not in encoded:
        raise InfrastructureFailure("Chroma read/write probe mismatch")


def cleanup_chroma(project: ComposeProject, probe: ProbeNames) -> None:
    collections = chroma_collections(chroma_json(project, "GET", CHROMA_COLLECTIONS_PATH))
    for collection in collections:
        if collection.get("name") == probe.chroma_collection:
            collection_id = chroma_collection_id(collection)
            chroma_http(
                project,
                "DELETE",
                f"{CHROMA_COLLECTIONS_PATH}/{collection_id}",
            )


def chroma_probe_collections(project: ComposeProject) -> tuple[str, ...]:
    collections = chroma_collections(chroma_json(project, "GET", CHROMA_COLLECTIONS_PATH))
    names = sorted(
        str(collection["name"])
        for collection in collections
        if isinstance(collection.get("name"), str)
        and str(collection["name"]).startswith("probe_")
    )
    return tuple(names)


def best_effort_cleanup(project: ComposeProject, probe: ProbeNames) -> None:
    for cleanup in (cleanup_postgres, cleanup_redis, cleanup_kafka, cleanup_chroma):
        try:
            cleanup(project, probe)
        except InfrastructureFailure:
            pass


def find_probe_artifacts(project: ComposeProject) -> tuple[str, ...]:
    artifacts: list[str] = []
    postgres_count = postgres_sql(
        project,
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema = 'runtime_probe' AND table_name LIKE 'probe_%';",
    )
    if postgres_count != "0":
        artifacts.append(f"PostgreSQL probe tables: {postgres_count}")

    redis_keys = redis_command(
        project,
        "--scan",
        "--pattern",
        "trialscribe:runtime-probe:*",
    )
    if redis_keys:
        artifacts.append(f"Redis probe keys: {redis_keys}")

    kafka_topics = kafka_script(project, "kafka-topics.sh", "--list")
    probe_topics = sorted(
        topic
        for topic in kafka_topics.splitlines()
        if topic.startswith("trialscribe-runtime-probe-")
    )
    if probe_topics:
        artifacts.append(f"Kafka probe topics: {', '.join(probe_topics)}")

    chroma_collections = chroma_probe_collections(project)
    if chroma_collections:
        artifacts.append(f"Chroma probe collections: {', '.join(chroma_collections)}")
    return tuple(artifacts)


def assert_cleanup(project: ComposeProject) -> None:
    deadline = time.monotonic() + CLEANUP_WAIT_SECONDS
    artifacts: tuple[str, ...] = ()
    while time.monotonic() < deadline:
        artifacts = find_probe_artifacts(project)
        if not artifacts:
            return
        time.sleep(0.5)
    raise InfrastructureFailure("probe cleanup failed\n" + "\n".join(artifacts))


def assert_no_published_ports(project: ComposeProject) -> None:
    rendered = project.run(
        "--profile",
        "infrastructure",
        "config",
        "--format",
        "json",
    )
    try:
        config = json.loads(rendered)
        services = config["services"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise InfrastructureFailure("Docker Compose returned an invalid config") from error

    published_services: list[str] = []
    for service_name in ("postgres", "redis", "kafka", "chroma"):
        service = services.get(service_name)
        if not isinstance(service, dict):
            raise InfrastructureFailure(
                f"Docker Compose config is missing the {service_name} service"
            )
        if service.get("ports"):
            published_services.append(service_name)

    if published_services:
        raise InfrastructureFailure(
            "test infrastructure publishes host ports: "
            + ", ".join(published_services)
        )


def wait_for_healthy(project: ComposeProject) -> None:
    project.run(
        "--profile",
        "infrastructure",
        "up",
        "-d",
        "--wait",
        "--wait-timeout",
        "120",
        "postgres",
        "redis",
        "kafka",
        "chroma",
        timeout=RESTART_TIMEOUT_SECONDS,
    )


def run_checks(project: ComposeProject, *, verify_restart: bool) -> None:
    probe = ProbeNames.create()
    try:
        prepare_postgres(project, probe)
        prepare_redis(project, probe)
        prepare_kafka(project, probe)
        prepare_chroma(project, probe)
        verify_postgres(project, probe)
        verify_redis(project, probe)
        verify_kafka(project, probe)
        verify_chroma(project, probe)

        if verify_restart:
            project.run(
                "restart",
                "postgres",
                "redis",
                "kafka",
                "chroma",
                timeout=RESTART_TIMEOUT_SECONDS,
            )
            wait_for_healthy(project)
            verify_postgres(project, probe)
            verify_redis(project, probe)
            verify_kafka(project, probe)
            verify_chroma(project, probe)

        print("healthy postgres read/write")
        print("healthy pgvector distance")
        print("healthy redis read/write")
        print("healthy kafka produce/consume")
        print("healthy chroma heartbeat")
        print("healthy chroma read/write")
    finally:
        best_effort_cleanup(project, probe)
    assert_cleanup(project)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check local runtime infrastructure")
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--compose-file", action="append", dest="compose_files")
    parser.add_argument("--verify-restart-persistence", action="store_true")
    parser.add_argument("--check-cleanup", action="store_true")
    parser.add_argument("--check-no-published-ports", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    compose_files = tuple(args.compose_files or ["docker-compose.yml"])
    project = ComposeProject(
        name=args.project_name,
        files=compose_files,
        redactions=read_redactions(),
    )
    try:
        if args.check_no_published_ports:
            assert_no_published_ports(project)
            print("healthy isolated infrastructure ports")
        elif args.check_cleanup:
            assert_cleanup(project)
            print("healthy probe cleanup")
        else:
            run_checks(project, verify_restart=args.verify_restart_persistence)
    except InfrastructureFailure as error:
        print(f"infrastructure check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
