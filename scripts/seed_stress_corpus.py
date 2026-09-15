#!/usr/bin/env python3
"""Seed a scaled-down synthetic corpus into a running release stack.

Feature 28 (stress-and-data-scale-validation) needs a reproducible corpus that
exercises the same bulk paths the roadmap's 1M-document target would use —
account registration, organization creation, conversation creation, and
document upload — without ever calling a real provider. Every document goes
through the real HTTP API, so the worker's existing chunk -> embed -> store
pipeline (trialscribe_worker.pipelines.index_document, which already batches
through EvidenceChunkRepository.add_many and ChromaIndex.upsert_many) does the
actual bulk indexing; this script does not re-implement it.

Run against an already-started release stack (see scripts.sh release up),
with the load overlay applied so gateway rate limits do not throttle a single
generator host standing in for many accounts:

    docker compose --env-file .env -p trialscribe-release \\
      -f docker-compose.yml -f infra/release/compose.yml -f infra/release/load.yml \\
      --profile infrastructure --profile release up -d --wait

    uv run --frozen --package trialscribe-worker \\
      python scripts/seed_stress_corpus.py --accounts 150 --conversations-per-org 4 \\
      --documents-per-conversation 3 --out infra/k6/results/seed-summary.json
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
HTTP_TIMEOUT_SECONDS = 40.0
MIN_AVAILABLE_MEMORY_MB = 1536
MEMORY_CHECK_EVERY = 20
REGISTER_PASSWORD = "a valid research stress passphrase"
LOREM_WORDS = (
    "protocol endpoint randomization stratified washout adverse dosing cohort "
    "biomarker titration crossover eligibility screening consent monitoring "
    "pharmacokinetic tolerability infusion placebo blinded investigator site "
    "enrollment safety efficacy visit schedule laboratory imaging adjudication"
).split()


class SeedFailure(RuntimeError):
    """A seeding step could not complete."""


class AbortedForMemory(RuntimeError):
    """The host's available memory fell below the safety floor."""


def available_memory_mb() -> float:
    with open("/proc/meminfo", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 1024
    raise SeedFailure("could not read MemAvailable from /proc/meminfo")


def guard_memory(floor_mb: float) -> None:
    current = available_memory_mb()
    if current < floor_mb:
        raise AbortedForMemory(
            f"available memory {current:.0f}MB fell below the {floor_mb:.0f}MB floor"
        )


def synthetic_paragraph(rng: random.Random, target_chars: int) -> str:
    words: list[str] = []
    length = 0
    while length < target_chars:
        word = rng.choice(LOREM_WORDS)
        words.append(word)
        length += len(word) + 1
    sentence = " ".join(words)
    return sentence[0].upper() + sentence[1:] + "."


def synthetic_research_document(rng: random.Random, index: int, min_chars: int, max_chars: int) -> bytes:
    target = rng.randint(min_chars, max_chars)
    heading = f"Synthetic evidence record {index}\n\n"
    body = synthetic_paragraph(rng, target - len(heading))
    return (heading + body).encode("utf-8")


def synthetic_trial_data(rng: random.Random, index: int, min_chars: int, max_chars: int) -> bytes:
    """Build a small JSON object the worker's trial-data extractor recognizes.

    trialscribe_worker.retrieval.extraction._flatten_trial reads these field
    names; filling them (rather than an arbitrary JSON blob) exercises the
    same flatten-to-text path a real uploaded trial record would.
    """

    target = rng.randint(min_chars, max_chars)
    payload = {
        "titleLong": f"Synthetic protocol {index}: {synthetic_paragraph(rng, 80)}",
        "phase": {"name": rng.choice(["Phase 1", "Phase 2", "Phase 3"])},
        "diseaseArea": {"name": rng.choice(["Oncology", "Cardiology", "Neurology"])},
        "therapeuticArea": {"name": rng.choice(["Immunology", "Metabolic disease"])},
        "routeOfAdministration": rng.choice(["Oral", "Intravenous", "Subcutaneous"]),
        "interventionGroups": synthetic_paragraph(rng, max(200, target // 6)),
        "objectivesAndEndpoints": synthetic_paragraph(rng, max(200, target // 4)),
        "inclusion": synthetic_paragraph(rng, max(200, target // 5)),
        "exclusion": synthetic_paragraph(rng, max(200, target // 5)),
    }
    return json.dumps(payload).encode("utf-8")


def http_json(
    method: str,
    url: str,
    *,
    body: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
    expected: tuple[int, ...] = (200,),
) -> dict[str, object]:
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
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise SeedFailure(f"{method} {url} failed: {error}") from error
    if status not in expected:
        raise SeedFailure(f"{method} {url} returned {status}, expected {expected}: {payload[:500]}")
    return json.loads(payload) if payload else {}


def http_multipart_upload(
    url: str,
    *,
    headers: dict[str, str],
    kind: str,
    filename: str,
    content: bytes,
    expected: tuple[int, ...] = (201,),
) -> dict[str, object]:
    boundary = uuid4().hex
    parts: list[bytes] = []
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(b'Content-Disposition: form-data; name="kind"\r\n\r\n')
    parts.append(kind.encode() + b"\r\n")
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
    )
    parts.append(b"Content-Type: text/plain\r\n\r\n")
    parts.append(content)
    parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    request_headers = dict(headers)
    request_headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    request = urllib.request.Request(url, data=body, method="POST", headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            status = int(response.status)
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        status = int(error.code)
        payload = error.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise SeedFailure(f"POST {url} failed: {error}") from error
    if status not in expected:
        raise SeedFailure(f"POST {url} returned {status}, expected {expected}: {payload[:500]}")
    return json.loads(payload) if payload else {}


@dataclass(slots=True)
class Tenant:
    """One seeded account, its organization, and its conversations."""

    email: str
    token: str
    organization_id: str
    conversation_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SeedCounts:
    accounts: int = 0
    organizations: int = 0
    conversations: int = 0
    documents: int = 0
    failed_documents: int = 0
    failed_accounts: int = 0
    started_at: float = 0.0
    finished_at: float = 0.0


def register_and_create_org(base_url: str, run_id: str, index: int) -> Tenant:
    email = f"stress-{run_id}-{index}@example.com"
    http_json(
        "POST",
        f"{base_url}/v1/auth/register",
        body={"email": email, "password": REGISTER_PASSWORD},
        expected=(201,),
    )
    login = http_json(
        "POST",
        f"{base_url}/v1/auth/login",
        body={"email": email, "password": REGISTER_PASSWORD},
        expected=(200,),
    )
    token = str(login["access_token"])
    auth_headers = {"Authorization": f"Bearer {token}"}
    org = http_json(
        "POST",
        f"{base_url}/v1/organizations",
        body={"name": f"Stress Org {index}"},
        headers=auth_headers,
        expected=(201,),
    )
    return Tenant(email=email, token=token, organization_id=str(org["id"]))


def create_conversations(base_url: str, tenant: Tenant, count: int) -> None:
    headers = {
        "Authorization": f"Bearer {tenant.token}",
        "X-Organization-ID": tenant.organization_id,
    }
    for index in range(count):
        conversation = http_json(
            "POST",
            f"{base_url}/v1/ai/conversations",
            body={"title": f"Stress conversation {index}"},
            headers=headers,
            expected=(201,),
        )
        tenant.conversation_ids.append(str(conversation["id"]))


def upload_documents(
    base_url: str,
    tenant: Tenant,
    documents_per_conversation: int,
    min_chars: int,
    max_chars: int,
    rng: random.Random,
) -> tuple[int, int]:
    headers = {
        "Authorization": f"Bearer {tenant.token}",
        "X-Organization-ID": tenant.organization_id,
    }
    uploaded = 0
    failed = 0
    for conversation_id in tenant.conversation_ids:
        for doc_index in range(documents_per_conversation):
            # One structured trial-data record per conversation (as a real
            # conversation would have), the rest free-text research documents.
            if doc_index == 0:
                kind = "trial_data"
                content = synthetic_trial_data(rng, doc_index, min_chars, max_chars)
                filename = f"synthetic-{doc_index}.json"
            else:
                kind = "research_document"
                content = synthetic_research_document(rng, doc_index, min_chars, max_chars)
                filename = f"synthetic-{doc_index}.txt"
            try:
                http_multipart_upload(
                    f"{base_url}/v1/ai/conversations/{conversation_id}/documents",
                    headers=headers,
                    kind=kind,
                    filename=filename,
                    content=content,
                    expected=(201,),
                )
                uploaded += 1
            except SeedFailure:
                failed += 1
    return uploaded, failed


def seed_tenant(
    base_url: str,
    run_id: str,
    index: int,
    conversations_per_org: int,
    documents_per_conversation: int,
    min_chars: int,
    max_chars: int,
) -> tuple[Tenant | None, int, int]:
    """Seed one account end to end; a failure here costs one tenant, not the run.

    Under concurrent load the auth service's Argon2id hashing can legitimately
    queue up against its CPU limit and a single registration can time out.
    That is itself a real capacity signal worth keeping, not a reason to crash
    every other in-flight tenant.
    """

    rng = random.Random(f"{run_id}-{index}")
    try:
        tenant = register_and_create_org(base_url, run_id, index)
        create_conversations(base_url, tenant, conversations_per_org)
    except SeedFailure as error:
        print(f"tenant {index} failed before documents: {error}", flush=True)
        return None, 0, 0
    uploaded, failed = upload_documents(
        base_url,
        tenant,
        documents_per_conversation,
        min_chars,
        max_chars,
        rng,
    )
    return tenant, uploaded, failed


def seed_corpus(
    base_url: str,
    *,
    accounts: int,
    conversations_per_org: int,
    documents_per_conversation: int,
    min_chars: int,
    max_chars: int,
    concurrency: int,
    memory_floor_mb: float,
) -> tuple[SeedCounts, list[Tenant]]:
    run_id = uuid4().hex[:10]
    counts = SeedCounts()
    tenants: list[Tenant] = []
    guard_memory(memory_floor_mb)
    counts.started_at = time.time()
    started = time.monotonic()
    pool = ThreadPoolExecutor(max_workers=concurrency)
    try:
        futures = [
            pool.submit(
                seed_tenant,
                base_url,
                run_id,
                index,
                conversations_per_org,
                documents_per_conversation,
                min_chars,
                max_chars,
            )
            for index in range(accounts)
        ]
        completed = 0
        for future in as_completed(futures):
            tenant, uploaded, failed = future.result()
            completed += 1
            if tenant is None:
                counts.failed_accounts += 1
            else:
                tenants.append(tenant)
                counts.accounts += 1
                counts.organizations += 1
                counts.conversations += len(tenant.conversation_ids)
                counts.documents += uploaded
                counts.failed_documents += failed
            if completed % MEMORY_CHECK_EVERY == 0 or completed == accounts:
                guard_memory(memory_floor_mb)
            if completed % max(1, accounts // 10) == 0 or completed == accounts:
                elapsed = time.monotonic() - started
                print(
                    f"seeded {completed}/{accounts} accounts, "
                    f"{counts.conversations} conversations, "
                    f"{counts.documents} documents ({elapsed:.0f}s elapsed)",
                    flush=True,
                )
    except AbortedForMemory:
        pool.shutdown(wait=True, cancel_futures=True)
        raise
    else:
        pool.shutdown(wait=True)
    counts.finished_at = time.time()
    return counts, tenants


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--accounts", type=int, default=150)
    parser.add_argument("--conversations-per-org", type=int, default=4)
    parser.add_argument("--documents-per-conversation", type=int, default=3)
    parser.add_argument("--min-doc-chars", type=int, default=6000)
    parser.add_argument("--max-doc-chars", type=int, default=9000)
    parser.add_argument("--concurrency", type=int, default=12)
    parser.add_argument("--memory-floor-mb", type=float, default=MIN_AVAILABLE_MEMORY_MB)
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "infra" / "k6" / "results" / "seed-summary.json"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        counts, tenants = seed_corpus(
            args.base_url,
            accounts=args.accounts,
            conversations_per_org=args.conversations_per_org,
            documents_per_conversation=args.documents_per_conversation,
            min_chars=args.min_doc_chars,
            max_chars=args.max_doc_chars,
            concurrency=args.concurrency,
            memory_floor_mb=args.memory_floor_mb,
        )
    except AbortedForMemory as error:
        print(f"seed aborted: {error}", file=sys.stderr)
        return 2
    except SeedFailure as error:
        print(f"seed failed: {error}", file=sys.stderr)
        return 1

    sample = next((tenant for tenant in tenants if tenant.conversation_ids), None)
    summary = {
        "base_url": args.base_url,
        "started_at": counts.started_at,
        "finished_at": counts.finished_at,
        "parameters": {
            "accounts": args.accounts,
            "conversations_per_org": args.conversations_per_org,
            "documents_per_conversation": args.documents_per_conversation,
            "min_doc_chars": args.min_doc_chars,
            "max_doc_chars": args.max_doc_chars,
        },
        "counts": {
            "accounts": counts.accounts,
            "failed_accounts": counts.failed_accounts,
            "organizations": counts.organizations,
            "conversations": counts.conversations,
            "documents_uploaded": counts.documents,
            "documents_failed_to_upload": counts.failed_documents,
        },
        "sample_account": (
            {
                "email": sample.email,
                "password": REGISTER_PASSWORD,
                "organization_id": sample.organization_id,
                "conversation_ids": sample.conversation_ids,
            }
            if sample is not None
            else None
        ),
        "all_conversation_ids": [
            conversation_id
            for tenant in tenants
            for conversation_id in tenant.conversation_ids
        ],
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote seed summary to {out_path}")
    print(
        "healthy seed corpus: "
        f"{counts.accounts} accounts, {counts.organizations} organizations, "
        f"{counts.conversations} conversations, {counts.documents} documents uploaded "
        f"({counts.failed_documents} failed)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
