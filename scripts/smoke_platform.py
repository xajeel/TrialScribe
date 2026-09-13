from __future__ import annotations

import http.client
import json
import os
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
WEB_ROOT = REPO_ROOT / "frontend" / "web"
POLL_TIMEOUT_SECONDS = 30.0
OUTPUT_LINE_LIMIT = 60
OUTPUT_CHARACTER_LIMIT = 1_000
PROVIDER_DEFAULTS = {
    "EMAIL": "smoke@example.invalid",
    "OPENAI_API_KEY": "smoke-openai-key",
    "TAVILY_API_KEY": "smoke-tavily-key",
    "NCBI_API_KEY": "smoke-ncbi-key",
}


class SmokeFailure(RuntimeError):
    """A platform boundary failed its process-level smoke check."""


class ProbeFailure(RuntimeError):
    """An HTTP probe could not confirm the expected response."""


@dataclass(frozen=True)
class Service:
    label: str
    package: str
    application: str
    service_name: str
    version: str
    port_key: str
    default_port: int


@dataclass
class CapturedProcess:
    process: subprocess.Popen[str]
    lines: deque[str]
    reader: threading.Thread
    redactions: tuple[str, ...]


SERVICES = (
    Service(
        label="gateway",
        package="trialscribe-gateway",
        application="trialscribe_gateway.api.app:app",
        service_name="api-gateway",
        version="0.1.0",
        port_key="GATEWAY_PORT",
        default_port=8000,
    ),
    Service(
        label="auth",
        package="trialscribe-auth",
        application="trialscribe_auth.api.app:app",
        service_name="auth-service",
        version="0.1.0",
        port_key="AUTH_PORT",
        default_port=8001,
    ),
    Service(
        label="user",
        package="trialscribe-user",
        application="trialscribe_user.api.app:app",
        service_name="user-service",
        version="0.1.0",
        port_key="USER_PORT",
        default_port=8002,
    ),
    Service(
        label="ai",
        package="trialscribe-ai",
        application="trialscribe_ai.api.app:app",
        service_name="ai-engine",
        version="2.0.0",
        port_key="AI_PORT",
        default_port=8003,
    ),
    Service(
        label="worker",
        package="trialscribe-worker",
        application="trialscribe_worker.api.app:app",
        service_name="worker-service",
        version="0.1.0",
        port_key="WORKER_PORT",
        default_port=8004,
    ),
)


def read_port(key: str, default: int) -> int:
    raw_port = os.environ.get(key, str(default))
    try:
        port = int(raw_port)
    except ValueError as error:
        raise SmokeFailure(f"{key} must be an integer") from error
    if not 1 <= port <= 65_535:
        raise SmokeFailure(f"{key} must be between 1 and 65535")
    return port


def capture_output(stream: TextIO, lines: deque[str]) -> None:
    for line in stream:
        lines.append(line.rstrip()[:OUTPUT_CHARACTER_LIMIT])


def start_process(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    redactions: tuple[str, ...] = (),
) -> CapturedProcess:
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            shell=False,
            start_new_session=True,
        )
    except OSError as error:
        raise SmokeFailure(f"could not start {command[0]}: {error}") from error

    if process.stdout is None:
        process.kill()
        raise SmokeFailure(f"could not capture output from {command[0]}")

    lines: deque[str] = deque(maxlen=OUTPUT_LINE_LIMIT)
    reader = threading.Thread(
        target=capture_output,
        args=(process.stdout, lines),
        daemon=True,
    )
    reader.start()
    return CapturedProcess(process, lines, reader, redactions)


def stop_process(child: CapturedProcess) -> None:
    process = child.process
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)

    child.reader.join(timeout=1)
    if process.stdout is not None:
        process.stdout.close()


def failure_output(child: CapturedProcess) -> str:
    output = "\n".join(child.lines) or "<no child output>"
    for value in child.redactions:
        if value:
            output = output.replace(value, "[redacted]")
    return output


def request(port: int, path: str) -> tuple[int, bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        body = response.read(1_048_577)
    except (OSError, http.client.HTTPException) as error:
        raise ProbeFailure(str(error)) from error
    finally:
        connection.close()

    if len(body) > 1_048_576:
        raise ProbeFailure("response exceeded one megabyte")
    return response.status, body


def require_health(port: int, path: str, expected: dict[str, str]) -> None:
    status, body = request(port, path)
    if status != 200:
        raise ProbeFailure(f"{path} returned HTTP {status}")
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ProbeFailure(f"{path} did not return JSON") from error
    if payload != expected:
        raise ProbeFailure(f"{path} returned an unexpected health body")


def wait_for_backend(child: CapturedProcess, service: Service, port: int) -> None:
    expected_live = {
        "status": "ok",
        "service": service.service_name,
        "version": service.version,
    }
    expected_ready = {
        "status": "ready",
        "service": service.service_name,
        "version": service.version,
    }
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    last_error = "service did not answer"

    while time.monotonic() < deadline:
        if child.process.poll() is not None:
            raise SmokeFailure(
                f"{service.label} exited before becoming healthy\n{failure_output(child)}"
            )
        try:
            require_health(port, "/health/live", expected_live)
            require_health(port, "/health/ready", expected_ready)
            return
        except ProbeFailure as error:
            last_error = str(error)
            time.sleep(0.1)

    raise SmokeFailure(
        f"{service.label} was not healthy within 30 seconds: {last_error}\n"
        f"{failure_output(child)}"
    )


def ai_environment() -> tuple[dict[str, str], tuple[str, ...]]:
    environment = os.environ.copy()
    for key, value in PROVIDER_DEFAULTS.items():
        if not environment.get(key):
            environment[key] = value
    redactions = tuple(environment[key] for key in PROVIDER_DEFAULTS)
    return environment, redactions


def smoke_backend(service: Service) -> None:
    port = read_port(service.port_key, service.default_port)
    environment: dict[str, str] | None = None
    redactions: tuple[str, ...] = ()
    if service.label == "ai":
        environment, redactions = ai_environment()

    command = ["uv", "run"]
    if service.label in {"gateway", "auth", "user"}:
        command.extend(("--env-file", str(REPO_ROOT / ".env")))
    command.extend(
        (
            "--package",
            service.package,
            "uvicorn",
            service.application,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        )
    )

    child = start_process(
        command,
        cwd=BACKEND_ROOT,
        env=environment,
        redactions=redactions,
    )
    try:
        wait_for_backend(child, service, port)
        print(f"healthy {service.label}")
    finally:
        stop_process(child)


def run_checked(command: list[str], *, cwd: Path, timeout: float) -> None:
    child = start_process(command, cwd=cwd)
    timed_out = False
    try:
        try:
            return_code = child.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            return_code = -1
        if timed_out:
            raise SmokeFailure(
                f"{command[0]} timed out\n{failure_output(child)}"
            )
        if return_code != 0:
            raise SmokeFailure(
                f"{command[0]} exited with status {return_code}\n{failure_output(child)}"
            )
    finally:
        stop_process(child)


def wait_for_web(child: CapturedProcess, port: int) -> None:
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    last_error = "preview did not answer"
    while time.monotonic() < deadline:
        if child.process.poll() is not None:
            raise SmokeFailure(
                f"web preview exited before becoming healthy\n{failure_output(child)}"
            )
        try:
            status, body = request(port, "/")
            if status != 200:
                raise ProbeFailure(f"web root returned HTTP {status}")
            if b"TrialScribe" not in body:
                raise ProbeFailure("web root did not contain TrialScribe")
            return
        except ProbeFailure as error:
            last_error = str(error)
            time.sleep(0.1)

    raise SmokeFailure(
        f"web was not healthy within 30 seconds: {last_error}\n{failure_output(child)}"
    )


def smoke_web() -> None:
    run_checked(["npm", "run", "build"], cwd=WEB_ROOT, timeout=120)
    port = read_port("WEB_SMOKE_PORT", 4173)
    child = start_process(
        [
            "npm",
            "run",
            "preview",
            "--",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--strictPort",
        ],
        cwd=WEB_ROOT,
    )
    try:
        wait_for_web(child, port)
        print("healthy web")
    finally:
        stop_process(child)


def main() -> int:
    try:
        for service in SERVICES:
            smoke_backend(service)
        smoke_web()
    except SmokeFailure as error:
        print(f"smoke failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
