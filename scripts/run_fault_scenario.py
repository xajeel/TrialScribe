#!/usr/bin/env python3
"""Exercise the fake chat provider's fault injection against a live release stack.

Feature 28 wants circuit breakers, retries, and partial-failure paths proven
under load, not just unit-tested. `provider_probe` is an existing job kind
(trialscribe_worker.pipelines.provider_probe) built exactly for this: it
calls the configured chat and embedding providers, stores the result, and
searches for it back through Chroma. This script submits a batch of those
jobs before, during, and after a fault window, and reads the outcome from
Prometheus (trialscribe_provider_circuit_state, trialscribe_jobs_total) so
the campaign can chart the breaker opening and recovering — all against the
in-process fake provider (backend/services/worker-service/trialscribe_worker/
providers/fake.py); no real provider is ever called.

Requires a running `trialscribe-release` Compose project (see scripts.sh
release up) and a seeded account with at least one conversation — the output
of scripts/seed_stress_corpus.py fits directly:

    uv run --frozen --package trialscribe-worker python scripts/run_fault_scenario.py \\
      --seed-summary infra/k6/results/seed-summary.json \\
      --out infra/k6/results/fault-scenario.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HTTP_TIMEOUT_SECONDS = 15.0
JOB_POLL_SECONDS = 1.0
JOB_POLL_TIMEOUT_SECONDS = 20.0
COMPOSE_WAIT_SECONDS = 180.0
CIRCUIT_OPEN_SECONDS = 30.0
RECOVERY_BUFFER_SECONDS = 8.0


class FaultScenarioFailure(RuntimeError):
    """The fault scenario could not run to completion."""


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


def http_json(
    method: str,
    url: str,
    *,
    body: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, object]]:
    """Return whatever status the server sent; callers decide what counts as ok."""

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
        raise FaultScenarioFailure(f"{method} {url} failed: {error}") from error
    return status, json.loads(payload) if payload else {}


@dataclass(slots=True)
class ComposeProject:
    name: str
    base_files: tuple[str, ...]

    def command(self, files: tuple[str, ...], *arguments: str) -> list[str]:
        command = ["docker", "compose", "--env-file", ".env", "-p", self.name]
        for compose_file in files:
            command.extend(["-f", compose_file])
        command.extend(["--profile", "infrastructure", "--profile", "release"])
        command.extend(arguments)
        return command

    def recreate_worker(self, *, with_fault: bool, extra_env: dict[str, str]) -> None:
        files = self.base_files
        if with_fault:
            files = (*files, "infra/release/fault.yml")
        environment = os.environ.copy()
        environment.update(extra_env)
        result = subprocess.run(
            self.command(
                files,
                "up",
                "-d",
                "--no-deps",
                "--wait",
                "--wait-timeout",
                "120",
                "worker",
                "jobs",
            ),
            cwd=REPO_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=COMPOSE_WAIT_SECONDS,
        )
        if result.returncode != 0:
            raise FaultScenarioFailure(
                f"could not recreate worker (fault={with_fault}): {result.stderr[-2000:]}"
            )


@dataclass(slots=True)
class ProbeOutcome:
    accepted: bool
    status: str | None
    seconds: float


def submit_probe(
    base_url: str,
    headers: dict[str, str],
    conversation_id: str,
) -> ProbeOutcome:
    started = time.monotonic()
    status_code, created = http_json(
        "POST",
        f"{base_url}/v1/jobs",
        body={
            "kind": "provider_probe",
            "conversation_id": conversation_id,
            "parameters": {"conversation_id": conversation_id},
        },
        headers=headers,
    )
    if status_code != 202:
        return ProbeOutcome(accepted=False, status=None, seconds=time.monotonic() - started)
    job_id = created["id"]
    deadline = time.monotonic() + JOB_POLL_TIMEOUT_SECONDS
    last_status = "unknown"
    while time.monotonic() < deadline:
        status_code, job = http_json(
            "GET",
            f"{base_url}/v1/jobs/{job_id}",
            headers=headers,
        )
        last_status = str(job.get("status", "unknown"))
        if last_status in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(JOB_POLL_SECONDS)
    return ProbeOutcome(accepted=True, status=last_status, seconds=time.monotonic() - started)


def run_phase(
    base_url: str,
    headers: dict[str, str],
    conversation_id: str,
    count: int,
) -> list[ProbeOutcome]:
    return [submit_probe(base_url, headers, conversation_id) for _ in range(count)]


def summarize(outcomes: list[ProbeOutcome]) -> dict[str, object]:
    accepted = [outcome for outcome in outcomes if outcome.accepted]
    succeeded = [outcome for outcome in accepted if outcome.status == "succeeded"]
    failed = [outcome for outcome in accepted if outcome.status == "failed"]
    timed_out = [
        outcome
        for outcome in accepted
        if outcome.status not in {"succeeded", "failed", "cancelled"}
    ]
    seconds = sorted(outcome.seconds for outcome in outcomes)

    def percentile(fraction: float) -> float:
        if not seconds:
            return 0.0
        index = min(len(seconds) - 1, int(len(seconds) * fraction))
        return seconds[index]

    return {
        "submitted": len(outcomes),
        "accepted": len(accepted),
        "succeeded": len(succeeded),
        "failed": len(failed),
        "still_open_after_poll_timeout": len(timed_out),
        "seconds_p50": percentile(0.5),
        "seconds_p95": percentile(0.95),
    }


def prometheus_query_range(
    prometheus_url: str,
    query: str,
    start: float,
    end: float,
    step: str,
) -> list[list[float]]:
    url = (
        f"{prometheus_url}/api/v1/query_range?query={urllib.parse.quote(query)}"
        f"&start={start}&end={end}&step={step}"
    )
    try:
        with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError) as error:
        raise FaultScenarioFailure(f"Prometheus query failed: {error}") from error
    results = payload.get("data", {}).get("result", [])
    if not results:
        return []
    values = results[0].get("values", [])
    return [[float(timestamp), float(value)] for timestamp, value in values]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--seed-summary", default=str(REPO_ROOT / "infra" / "k6" / "results" / "seed-summary.json"))
    parser.add_argument("--project-name", default="trialscribe-release")
    parser.add_argument("--jobs-per-phase", type=int, default=10)
    parser.add_argument("--fault-delay-seconds", default="0.2")
    parser.add_argument("--fault-error", default="rate_limited", choices=("timeout", "rate_limited", "error"))
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "infra" / "k6" / "results" / "fault-scenario.json"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dotenv = read_dotenv()
    gateway_port = env_value(dotenv, "GATEWAY_PORT", "8000")
    prometheus_port = env_value(dotenv, "PROMETHEUS_PORT", "9090")
    base_url = args.base_url or f"http://127.0.0.1:{gateway_port}"
    prometheus_url = f"http://127.0.0.1:{prometheus_port}"

    seed_summary = json.loads(Path(args.seed_summary).read_text(encoding="utf-8"))
    sample = seed_summary.get("sample_account")
    if not sample or not sample.get("conversation_ids"):
        print("fault scenario failed: seed summary has no sample account/conversation", file=sys.stderr)
        return 1

    status_code, login = http_json(
        "POST",
        f"{base_url}/v1/auth/login",
        body={"email": sample["email"], "password": sample["password"]},
    )
    if status_code != 200:
        print(f"fault scenario failed: could not log in seeded account ({status_code})", file=sys.stderr)
        return 1
    headers = {
        "Authorization": f"Bearer {login['access_token']}",
        "X-Organization-ID": sample["organization_id"],
    }
    conversation_id = sample["conversation_ids"][0]

    project = ComposeProject(
        name=args.project_name,
        base_files=("docker-compose.yml", "infra/release/compose.yml"),
    )

    print("phase 1/4: baseline (no fault)", flush=True)
    baseline_start = time.time()
    baseline = run_phase(base_url, headers, conversation_id, args.jobs_per_phase)
    baseline_end = time.time()

    print("phase 2/4: injecting rate_limited faults into the fake chat provider", flush=True)
    project.recreate_worker(
        with_fault=True,
        extra_env={
            "STRESS_FAULT_DELAY_SECONDS": args.fault_delay_seconds,
            "STRESS_FAULT_ERROR": args.fault_error,
            "STRESS_FAULT_FAIL_TIMES": "0",
        },
    )
    fault_start = time.time()
    faulted = run_phase(base_url, headers, conversation_id, args.jobs_per_phase)
    fault_end = time.time()

    print("phase 3/4: clearing the fault and waiting for the circuit to close", flush=True)
    project.recreate_worker(with_fault=False, extra_env={})
    time.sleep(CIRCUIT_OPEN_SECONDS + RECOVERY_BUFFER_SECONDS)

    print("phase 4/4: recovery (no fault)", flush=True)
    recovery_start = time.time()
    recovered = run_phase(base_url, headers, conversation_id, args.jobs_per_phase)
    recovery_end = time.time()

    try:
        circuit_series = prometheus_query_range(
            prometheus_url,
            'trialscribe_provider_circuit_state{provider="fake"}',
            baseline_start - 10,
            recovery_end + 10,
            "10s",
        )
    except FaultScenarioFailure as error:
        print(f"warning: could not read circuit state from Prometheus: {error}", file=sys.stderr)
        circuit_series = []

    results = {
        "base_url": base_url,
        "conversation_id": conversation_id,
        "fault": {
            "delay_seconds": args.fault_delay_seconds,
            "error": args.fault_error,
        },
        "phases": {
            "baseline": {
                "started_at": baseline_start,
                "finished_at": baseline_end,
                **summarize(baseline),
            },
            "faulted": {
                "started_at": fault_start,
                "finished_at": fault_end,
                **summarize(faulted),
            },
            "recovery": {
                "started_at": recovery_start,
                "finished_at": recovery_end,
                **summarize(recovered),
            },
        },
        "circuit_state_series": circuit_series,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"wrote fault scenario results to {out_path}")
    print(
        "healthy fault scenario: "
        f"baseline succeeded {results['phases']['baseline']['succeeded']}/{args.jobs_per_phase}, "
        f"faulted succeeded {results['phases']['faulted']['succeeded']}/{args.jobs_per_phase}, "
        f"recovery succeeded {results['phases']['recovery']['succeeded']}/{args.jobs_per_phase}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
