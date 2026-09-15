# TrialScribe Worker Service

The worker service is where the clinical-writing work actually happens. Other services accept
requests, store state, or route traffic; the worker indexes an uploaded protocol document,
searches PubMed and a shortlist of medical websites for supporting evidence, drafts an ICH M11
section with citations a reviewer can check, and assembles the finished Word export. It runs as
an independent Python application and, unlike the other backend services, ships as two separate
processes that share one codebase.

For a simple mental model, imagine a request desk with a back office:

- Other services hand the worker a ticket: "index this file," "draft section 4," "check whether
  this protocol is ready to export."
- The ticket is written to PostgreSQL and a Kafka queue in one indivisible step.
- One process, the job runtime, is the only one that reads the queue and does the work.
- A second, smaller process, the HTTP API, lets the front desk create a ticket, check its
  status, cancel it, or download what it produced. It never does the work itself.

## Service boundary

`./scripts.sh run worker` starts `trialscribe_worker.api.app`, a FastAPI application on port
`8004`. It has no queue reader and no provider connections; it only reads and writes job
tickets, generation attempts, usage totals, readiness snapshots, and exports already sitting in
PostgreSQL or Redis. `./scripts.sh run jobs` starts `trialscribe_worker.runtime.main`, which
owns every external connection the work itself needs — PostgreSQL, Redis, Kafka, Chroma, and the
configured chat/embedding providers — and is the only process that ever executes a pipeline.
Both must be running for background work to complete: the API accepts and reports on tickets,
the runtime consumes them.

The HTTP API is more than a health check. Besides `GET /health/live` and `GET /health/ready`,
`trialscribe_worker/api/jobs.py` exposes a `/jobs` router:

| Method | Route | Purpose |
|---|---|---|
| `POST` | `/jobs` | Create a job ticket and enqueue it |
| `GET` | `/jobs` | List a conversation's tickets, newest first |
| `GET` | `/jobs/{id}` | Read one ticket, with live progress |
| `POST` | `/jobs/{id}/cancel` | Cancel a queued ticket outright, or ask a running one to stop |
| `GET` | `/jobs/{id}/attempts` | Read the latest per-section generation outcome for a job |
| `GET` | `/jobs/{id}/rewrite-options` | Read the alternative drafts a rewrite job proposed |
| `GET` | `/jobs/readiness` | Read the latest protocol readiness snapshot |
| `GET` | `/jobs/usage` | Read token and cost totals for a conversation |
| `GET` | `/jobs/exports` | List stored Word exports for a conversation |
| `GET` | `/jobs/exports/{id}/file` | Download one stored export |

Every route reads `X-TrialScribe-Account-ID` and `X-TrialScribe-Organization-ID`, the same
trusted headers the gateway writes for AI Engine calls, so the worker never re-verifies
membership itself.

The worker does not own every table it touches. It owns `jobs`, `evidence_chunks`,
`provider_calls`, `section_generation_attempts`, `protocol_exports`, and
`protocol_readiness_checks` — all under the shared `trialscribe` PostgreSQL schema. It also
reads and writes `trialscribe.conversations`, `trialscribe.documents`, and
`trialscribe.m11_sections`, tables owned by other services' migrations, through plain SQL rather
than by importing their application code. This is why `trialscribe_worker/models/job.py` states
its tenant and conversation columns are enforced by foreign keys the worker's own migration
declares, pointing at tables the worker's Python package cannot see.

## Job kinds and the event flow

`JobKind` names seven kinds of work: `probe`, `provider_probe`, `index_document`,
`research_web`, `generate_sections`, `validate_readiness`, and `export_protocol`.
`trialscribe_worker/runtime/main.py` maps each kind to a pipeline function from
`trialscribe_worker/pipelines/`. `probe` and `provider_probe` exist to exercise the runtime and
the provider gateway end to end without touching real trial content; the other five are the
product pipelines.

A ticket reaches the runtime one of two ways. A user action (through the gateway) calls
`POST /jobs`, and `JobService.request_job` (`trialscribe_worker/services/jobs.py`) writes the
job row and its `job.requested` event into the outbox in the same transaction — never publishing
directly, since a crash between "write the ticket" and "publish the message" would otherwise
either lose the message or hand out a ticket nobody committed. A background relay (or, for a
freshly created job, an inline `drain_once()` call) hands the outbox row to Kafka shortly after.
The other route is automatic: when AI Engine publishes `document.uploaded`,
`trialscribe_worker/pipelines/document_events.py` reacts by calling the same `request_job` to
enqueue an `index_document` job; `document.deleted` instead removes that document's evidence
chunks directly, with no job involved.

`trialscribe_worker/services/job_runner.py` is what turns a `job.requested` record into a
result. `JobRunner.handle` first claims the ticket — an update that only succeeds while the
job's status is `queued`, `running`, or `retrying`, and that bumps the attempt counter and sets
`running`. A job already `succeeded`, `failed`, or `cancelled` is not claimed again, which is
what makes a redelivered event harmless. The claimed job's `kind` selects a pipeline from the
map built in `runtime/main.py`; an unrecognized kind fails immediately with
`unsupported_kind`. The pipeline is then handed a `JobContext` carrying its parameters, a
`report(percent)` callback that publishes progress to Redis and periodically persists it to
PostgreSQL, and a `check_cancelled()` callback pipelines call between steps.

Retries happen at two layers. The shared event consumer (`trialscribe_events/consumer.py`)
retries a failing handler up to `max_delivery_attempts` (3 by default) with jittered backoff
before writing the record to a dead-letter topic; each of those retries is a fresh call into
`JobRunner.handle`, so each one reclaims the ticket and increments its attempt count. Below
`max_delivery_attempts`, a failed attempt is parked as `retrying`; on the last attempt the job is
instead marked `failed` with error code `handler_failed` (or `cancelled`, if the pipeline raised
because a cancellation was requested). That terminal write happens in the same transaction as
the event consumer's own record of having handled the event — a table named
`processed_events`, keyed by consumer group and event id, that is how the event backbone
deduplicates redelivery. If the job write were to roll back, the "already handled" receipt
rolls back with it, so the two can never disagree about whether the job's outcome is final.

Pipeline-specific failures are recorded at a finer grain than the ticket's own
`handler_failed`/`unsupported_kind`/`cancelled` error code: `index_document` writes a status and
reason onto the document row itself (`document could not be processed`, `document contained no
extractable text`, `document indexing failed`), and `generate_sections` writes one row per
section attempt with its own error code (`missing_section`, `empty_output`,
`provider_failed`, `revision_conflict`, `invalid_selection`).

## The provider gateway

Every chat and embedding call, from every pipeline, goes through
`trialscribe_worker/providers/gateway.py`. Nothing calls a provider client directly —
`pipelines/scope.py`'s `require_gateway` refuses to let a pipeline run without one. The gateway
applies, in order: a per-operation `asyncio.Semaphore` (`provider_max_concurrency`, 8 by
default) so one job cannot starve every other job's calls; an overall `asyncio.timeout`
(`provider_timeout_seconds`, 30s); `retry_call`, which retries a timeout, rate limit, or
transport failure up to `provider_retry_attempts` times (3) with full-jitter exponential
backoff; and a `CircuitBreaker` per operation (chat and embed each get their own) that opens
after `circuit_failure_threshold` consecutive retryable failures (5) and stays open for
`circuit_open_seconds` (30s) before allowing calls through again to test whether the provider
has recovered. A non-retryable error
(a bad request, an unsupported model) is not retried and does not count toward the breaker.

`trialscribe_worker/providers/factory.py` builds the configured backend from
`WORKER_CHAT_PROVIDER` and `WORKER_EMBEDDING_PROVIDER`: `fake` for both by default, `deepseek`
(via the OpenAI-compatible SDK, `providers/deepseek.py`) for chat, and `fastembed` (a local
sentence-embedding model, `providers/fastembed.py`) for embeddings. `providers/fake.py`'s
`FakeChatProvider` echoes the last user message back as `echo:<content>`, and
`FakeEmbeddingProvider` returns a deterministic 384-dimension vector derived from a SHA-256 hash
of the input text, so the same text always embeds to the same vector without a model file or
network call. Both fakes accept an optional `FakeFault` — a delay, an error to raise
(`timeout`, `rate_limited`, or `unavailable`), and how many calls should fail before succeeding
— configured through `WORKER_FAKE_CHAT_FAULT_*` environment variables, which is how a stress
campaign exercises retries and circuit breaking without a real provider.

Every call is metered whether it succeeds or fails: `gateway._meter` builds a
`ProviderCallRecord` (provider, operation, model, token counts, latency, outcome, and a cost in
micros looked up from `providers/model_catalog.py`) and hands it to a `UsageRecorder`. In
production that is `PostgresUsageRecorder` (`repositories/provider_calls.py`), which inserts
into `trialscribe.provider_calls` in its own short transaction so a metering failure never
undoes a provider call that already succeeded. Each request carries an `idempotency_key` built
from the job id, attempt number, and a description of the specific call (an embed batch index, a
section number, a retrieve query hash); the table has a unique index on that key for successful
rows, and the gateway checks for an existing successful row before making a chat call at all —
a repeat of the exact same key is answered from the stored token and cost figures rather than
billed twice (with an empty result text, since the usage table stores token counts, not the
generated text). Embedding calls are never answered this way — there are no stored vectors to
replay a search against — so every embed call reaches the provider.

## RAG indexing and retrieval

`retrieval/extraction.py` turns stored file bytes into plain text: UTF-8 text and Markdown pass
through as-is, PDFs are read with `pypdf` (an encrypted PDF is refused), and the structured
trial-data JSON format is flattened into labelled lines (title, phase, disease area,
interventions, inclusion/exclusion criteria, and so on), falling back to a raw JSON dump if
nothing recognizable was found. `retrieval/chunking.py`'s `chunk_text` then splits that text into
overlapping spans — `chunk_size_chars`/`chunk_overlap_chars` default to 1200/200 — preferring to
break on a paragraph, then a sentence, then a word boundary rather than mid-word. For PDFs, a
`PageLocator` maps each chunk's character offset back to a 1-based page number using a binary
search over the page spans extraction recorded.

`index_document` (`pipelines/index_document.py`) runs extract, then chunk, then embed in
batches of `embed_batch_size` (32) through the gateway, then calls `EvidenceIndex.put_many` to
store the batch. Storage is tenant-scoped and split across two stores:
`repositories/evidence_chunks.py` writes the passage text, its character span, page number, and
provenance (`source_kind`/`source_identity`) into PostgreSQL, which remains the source of truth,
while `retrieval/chroma_index.py`'s `ChromaIndex` upserts only the vector and the chunk id into
Chroma. Chroma organizes vectors into one collection per conversation, named `c<conversation
hex>` — every conversation's evidence lives in its own collection — and every write and query
additionally carries an explicit `organization_id`/`conversation_id` filter, so a query can never
cross a tenant boundary even if it somehow reached the wrong collection. Before replacing a
document's chunks (on re-index or delete), `EvidenceIndex.drop_source` removes the old vectors
from Chroma and the old rows from PostgreSQL by `source_kind`/`source_identity`.

Retrieval mirrors that split. `retrieval/retriever.py`'s `ConversationRetriever` embeds the
query text (through the same gateway, so it is metered and idempotency-keyed like any other
call) and calls `EvidenceIndex.search`, which queries Chroma for the nearest `k` chunk ids
(`retrieve_k` defaults to 8) scoped to the tenant, then loads the matching rows from PostgreSQL
by id. A chunk id Chroma still has but PostgreSQL no longer owns — for instance, one deleted in
a race with a query — is silently dropped rather than returned, since PostgreSQL is what
resolves a citation later.

## Web research evidence

`research_web` searches two sources for a conversation-supplied query:
`retrieval/pubmed.py`'s `PubMedClient` calls NCBI's `esearch` then `efetch` endpoints and parses
the returned XML into title, abstract, publication date, and a PubMed URL; and
`retrieval/tavily.py`'s `TavilyClient` posts to Tavily's search API restricted to
`include_domains`, an allow-list of roughly a hundred medical, regulatory, and clinical
research domains (`retrieval/web_allowlist.py`) such as `fda.gov`, `nih.gov`, `cdc.gov`,
`clinicaltrials.gov`, `nature.com`, `mayoclinic.org`, and `sciencedirect.com`. Tavily returns no
results at all, rather than an error, when no API key is configured; PubMed and Tavily each
retry a `429` or `5xx` response up to `research_retry_attempts` times before giving up.

The pipeline (`pipelines/research_web.py`) runs both searches, then merges the hits: each result
is reduced to a canonical URL, PubMed hits are kept unconditionally, and web hits are kept only
if their host is still on the allow-list — checked again here even though Tavily was already
asked to restrict to those domains. Duplicate URLs (from either source) keep only the first hit
seen. Each kept page is formatted into one passage (title, URL, publication date, retrieval
date, and body), chunked, embedded, and stored through the same `EvidenceIndex` used for
uploaded documents, under `source_kind="web"` and a `source_identity` derived from the URL. If
neither source returned anything and at least one of them actually errored, the job itself is
recorded as failed; a search that legitimately found nothing is not an error.

Because web and PubMed passages land in the same evidence store as uploaded trial documents —
distinguished only by `source_kind` — retrieval for section drafting treats them uniformly: a
single `search` call over one conversation's Chroma collection can return uploaded, PubMed, and
web passages side by side. The one place `source_kind` is filtered explicitly is the trial-data
summary block built for the generation prompt, which pulls only `trial_data` chunks so the model
sees the trial's own structured facts as a distinct block from retrieved supporting evidence.

## Citation-backed generation and export

`generate_sections` (`pipelines/generate_sections.py`) drafts one or more of the 14 catalogued
M11 section numbers. For each requested section it first checks that the section exists, is not
already `done`, and that the caller's `expected_revision` still matches the stored
`current_revision` — an optimistic-concurrency guard against two callers editing the same
section at once; a mismatch is recorded as `skipped`, not retried. It retrieves evidence for the
section's title and instructions, then builds a prompt
(`prompts/section_generation.py`) whose system message tells the model plainly that retrieved
evidence and uploaded documents are untrusted data, never instruction, and that it may cite a
supporting passage only with a `[cite:<uuid>]` marker using an id drawn from the evidence it was
given. After the model responds, `retrieval/citations.py`'s `apply_citations` strips any
citation marker whose id is not among the chunks actually retrieved for that call — a bound
against the model citing an id it invented or remembered from elsewhere. An empty result after
that cleanup is recorded as a failure (`empty_output`); otherwise the draft is saved with
`revise_draft`, which itself re-checks `expected_revision` and fails the attempt
(`revision_conflict`) rather than overwrite a section someone else changed in the meantime. The
same pipeline also serves a `rewrite` mode: given one section, an instruction, and an optional
character-offset selection, it produces two alternative rewrites — one told to keep a similar
length, one told to tighten the wording — without saving either; the caller chooses one through
the conversation UI. Sections in a `generate_sections` job succeed or fail independently; the job
itself ends failed if any section failed, so a caller can re-request just the sections still
empty rather than redo ones that already landed.

`validate_readiness` (`pipelines/validate_readiness.py`) is a read-only scoring pass: it checks
that all 14 sections exist, are `done`, and are non-empty; that no uploaded source is still
`pending` or `failed`; that no section's citations point at evidence no longer resolvable; and
that no section's latest generation attempt failed. It writes one snapshot row
(`protocol_readiness_checks`) that both the `/jobs/readiness` endpoint and `export_protocol`
read back rather than recomputing.

`export_protocol` (`pipelines/export_protocol.py`) does not draft or edit any section text. It
loads the latest readiness snapshot and refuses to export if none exists or if the conversation
has had activity since the snapshot was computed (a stale check); an export scoped to
`done_only` additionally refuses unless the snapshot says the protocol is ready. It collects the
sections in scope (`done_only`, or `done` plus `draft`), gathers every citation id they
reference, loads just those evidence chunks, and calls
`services/protocol_docx.py`'s `build_protocol_docx` to assemble a `python-docx` Word document: a
title page, one heading per section (marked "(Draft)" when not yet done), body text with
`[cite:<uuid>]` markers replaced by sequential `[1]`, `[2]`, … numbers in first-appearance order,
and a closing References section listing each numbered source's kind, identity, and page number
where known. The resulting bytes are stored in `protocol_exports` and served back through
`GET /jobs/exports/{id}/file`.

## Running locally

Bootstrap the environment and infrastructure once, from the repository root:

```bash
./scripts.sh env
./scripts.sh install
./scripts.sh infra up
./scripts.sh db migrate
```

The worker needs both of its processes running. In separate terminals:

```bash
./scripts.sh run worker   # HTTP API on port 8004 (WORKER_PORT)
./scripts.sh run jobs     # Kafka consumer + pipelines — trialscribe_worker.runtime.main
```

`WORKER_CHAT_PROVIDER` and `WORKER_EMBEDDING_PROVIDER` default to `fake` in `.env_example`, so
`./scripts.sh run jobs` drafts sections, embeds text, and passes through the provider gateway's
full retry and circuit-breaking logic without any external API key. To exercise the real chat
model, set `WORKER_CHAT_PROVIDER=deepseek` and `DEEPSEEK_API_KEY`; to embed with a real local
model instead of the deterministic fake, set `WORKER_EMBEDDING_PROVIDER=fastembed`. Web research
needs its own keys regardless of the chat/embedding provider: `TAVILY_API_KEY` for website
search (Tavily returns no web results at all without one) and `NCBI_API_KEY` for PubMed, which
is included on requests when set but is not required for PubMed search to work.

`./scripts.sh jobs test` runs an isolated, disposable integration check of the background job
runtime against its own Postgres/Redis/Kafka containers, then removes them. The job runtime also
publishes Prometheus metrics on its own port (`WORKER_JOBS_METRICS_PORT`, 8006 by default),
separate from the HTTP API's port.
