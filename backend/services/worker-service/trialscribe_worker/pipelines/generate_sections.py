"""Draft requested M11 sections from tenant-scoped evidence with citations.

One implementation serves both callers. `generate_sections_pipeline` takes a
store scope: in production that scope opens a short database transaction per
unit of work, so no SQL transaction stays open across a chat completion; in
tests it hands back in-memory doubles. The drafting rules live in one place, so
what the tests prove is what production runs.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from trialscribe_db.runtime import DatabaseRuntime

from trialscribe_worker.config import WorkerSettings, worker_settings
from trialscribe_worker.models.evidence_chunk import EvidenceChunk
from trialscribe_worker.models.m11_section_record import M11SectionRecord
from trialscribe_worker.pipelines.scope import (
    AttemptStore,
    BoundScope,
    GenerationScope,
    GenerationStores,
    TransactionScope,
    generation_stores_from,
    require_gateway,
)
from trialscribe_worker.prompts.section_generation import (
    section_generation_messages,
    section_rewrite_messages,
)
from trialscribe_worker.providers.gateway import ProviderGateway
from trialscribe_worker.providers.types import ChatRequest
from trialscribe_worker.retrieval.chroma_index import ChromaIndex
from trialscribe_worker.retrieval.citations import apply_citations, parse_cite_ids
from trialscribe_worker.retrieval.retriever import ConversationRetriever
from trialscribe_worker.services.job_runner import JobContext
from trialscribe_worker.utils.constant import (
    EVIDENCE_SOURCE_TRIAL_DATA,
    GENERATE_EXPECTED_REVISIONS_PARAMETER,
    GENERATE_MEMORY_TURN_LIMIT,
    GENERATE_MODE_GENERATE,
    GENERATE_MODE_PARAMETER,
    GENERATE_MODE_REWRITE,
    GENERATE_SECTION_NUMBERS,
    GENERATE_SECTIONS_PARAMETER,
    M11_REVISION_ACTION_GENERATED,
    M11_SECTION_DONE_STATUS,
    REWRITE_ALTERNATIVE_COUNT,
    REWRITE_INSTRUCTION_MAX_LENGTH,
    REWRITE_INSTRUCTION_PARAMETER,
    REWRITE_KEEP_CITATIONS_PARAMETER,
    REWRITE_OPTIONS_KIND,
    REWRITE_SELECTION_END_PARAMETER,
    REWRITE_SELECTION_START_PARAMETER,
    REWRITE_USE_SOURCES_PARAMETER,
    REWRITE_VARIANT_HINTS,
)
from trialscribe_worker.utils.enum import GenerationAttemptStatus, GenerationErrorCode
from trialscribe_worker.utils.exceptions import (
    GenerateSectionError,
    InvalidJobInputError,
    ProviderCircuitOpenError,
    ProviderConfigError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    WorkerServiceError,
)

_PROVIDER_ERRORS = (
    ProviderTimeoutError,
    ProviderUnavailableError,
    ProviderRateLimitedError,
    ProviderCircuitOpenError,
    ProviderConfigError,
)

_START_PERCENT = 10
_WORK_PERCENT = 80
_DONE_PERCENT = 100

_SUCCEEDED = GenerationAttemptStatus.SUCCEEDED.value
_SKIPPED = GenerationAttemptStatus.SKIPPED.value
_FAILED = GenerationAttemptStatus.FAILED.value


def parse_generate_request(parameters: dict[str, object]) -> list[tuple[str, int]]:
    """Return ordered (section_number, expected_revision) pairs, or refuse."""

    numbers = parameters.get(GENERATE_SECTIONS_PARAMETER)
    expected = parameters.get(GENERATE_EXPECTED_REVISIONS_PARAMETER)
    if not isinstance(numbers, list) or not numbers:
        raise InvalidJobInputError
    if any(not isinstance(item, str) for item in numbers):
        raise InvalidJobInputError
    if len(set(numbers)) != len(numbers):
        raise InvalidJobInputError
    if any(item not in GENERATE_SECTION_NUMBERS for item in numbers):
        raise InvalidJobInputError
    if not isinstance(expected, dict):
        raise InvalidJobInputError
    pairs: list[tuple[str, int]] = []
    for number in numbers:
        if number not in expected:
            raise InvalidJobInputError
        revision = expected[number]
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise InvalidJobInputError
        pairs.append((number, revision))
    return pairs


@dataclass(frozen=True)
class RewriteRequest:
    """One draft section to rewrite, with optional selected offsets."""

    section_number: str
    expected_revision: int
    instruction: str
    selection_start: int | None
    selection_end: int | None
    keep_citations: bool
    use_sources: bool


def _optional_bool(parameters: dict[str, object], key: str, default: bool) -> bool:
    if key not in parameters:
        return default
    value = parameters[key]
    if not isinstance(value, bool):
        raise InvalidJobInputError
    return value


def parse_rewrite_request(parameters: dict[str, object]) -> RewriteRequest:
    """Return a single-section rewrite request, or refuse."""

    mode = parameters.get(GENERATE_MODE_PARAMETER, GENERATE_MODE_GENERATE)
    if mode != GENERATE_MODE_REWRITE:
        raise InvalidJobInputError
    pairs = parse_generate_request(parameters)
    if len(pairs) != 1:
        raise InvalidJobInputError
    instruction = parameters.get(REWRITE_INSTRUCTION_PARAMETER)
    if not isinstance(instruction, str):
        raise InvalidJobInputError
    trimmed = instruction.strip()
    if not 1 <= len(trimmed) <= REWRITE_INSTRUCTION_MAX_LENGTH:
        raise InvalidJobInputError
    start = parameters.get(REWRITE_SELECTION_START_PARAMETER)
    end = parameters.get(REWRITE_SELECTION_END_PARAMETER)
    if start is None and end is None:
        selection_start, selection_end = None, None
    else:
        if isinstance(start, bool) or isinstance(end, bool):
            raise InvalidJobInputError
        if not isinstance(start, int) or not isinstance(end, int) or start >= end:
            raise InvalidJobInputError
        selection_start, selection_end = start, end
    return RewriteRequest(
        section_number=pairs[0][0],
        expected_revision=pairs[0][1],
        instruction=trimmed,
        selection_start=selection_start,
        selection_end=selection_end,
        keep_citations=_optional_bool(
            parameters, REWRITE_KEEP_CITATIONS_PARAMETER, True
        ),
        use_sources=_optional_bool(parameters, REWRITE_USE_SOURCES_PARAMETER, True),
    )


def _job_mode(parameters: dict[str, object]) -> str:
    mode = parameters.get(GENERATE_MODE_PARAMETER, GENERATE_MODE_GENERATE)
    if mode not in {GENERATE_MODE_GENERATE, GENERATE_MODE_REWRITE}:
        raise InvalidJobInputError
    return str(mode)


@dataclass(frozen=True, slots=True)
class _SectionPlan:
    """What one section needs before any provider is called."""

    outcome: str | None
    record: M11SectionRecord | None = None
    query: str = ""
    memory: tuple[tuple[str, str], ...] = ()


async def _record(
    context: JobContext,
    attempts: AttemptStore,
    section_number: str,
    status: str,
    *,
    model: str | None = None,
    prompt: str | None = None,
    content: str | None = None,
    error_code: str | None = None,
    citation_ids: list[str] | None = None,
) -> None:
    """Write exactly one row describing what this section attempt did."""

    if context.conversation_id is None:
        raise InvalidJobInputError
    await attempts.add(
        organization_id=context.organization_id,
        conversation_id=context.conversation_id,
        job_id=context.job_id,
        attempt=context.attempt,
        section_number=section_number,
        status=status,
        model=model,
        prompt=prompt,
        content=content,
        error_code=error_code,
        citation_ids=citation_ids or [],
    )


def _retrieval_query(record: M11SectionRecord) -> str:
    if record.instructions.strip():
        return f"{record.title}\n{record.instructions}"
    return record.title


def _trial_passages(evidence: list[EvidenceChunk]) -> list[str]:
    return [
        chunk.text for chunk in evidence if chunk.source_kind == EVIDENCE_SOURCE_TRIAL_DATA
    ]


async def _plan_section(
    context: JobContext,
    stores: GenerationStores,
    section_number: str,
    expected_revision: int,
) -> _SectionPlan:
    """Decide whether this section may be drafted, and gather what drafting needs.

    Everything here is a read except the attempt row written when the answer is
    no, which is why it belongs in one short scope of its own.
    """

    record = await stores.sections.get_scoped(
        context.organization_id,
        context.conversation_id,  # type: ignore[arg-type]
        section_number,
    )
    if record is None:
        await _record(
            context,
            stores.attempts,
            section_number,
            _FAILED,
            error_code=GenerationErrorCode.MISSING_SECTION.value,
        )
        return _SectionPlan(outcome=_FAILED)
    if record.status == M11_SECTION_DONE_STATUS:
        await _record(context, stores.attempts, section_number, _SKIPPED)
        return _SectionPlan(outcome=_SKIPPED)
    if record.current_revision != expected_revision:
        await _record(
            context,
            stores.attempts,
            section_number,
            _SKIPPED,
            error_code=GenerationErrorCode.REVISION_CONFLICT.value,
        )
        return _SectionPlan(outcome=_SKIPPED)
    turns = await stores.memory.recent(
        context.organization_id,
        context.conversation_id,  # type: ignore[arg-type]
        GENERATE_MEMORY_TURN_LIMIT,
    )
    return _SectionPlan(
        outcome=None,
        record=record,
        query=_retrieval_query(record),
        memory=tuple(turns),
    )


async def _retrieve(
    context: JobContext,
    gateway: ProviderGateway,
    stores: GenerationStores,
    settings: WorkerSettings,
    query: str,
) -> list[EvidenceChunk]:
    retriever = ConversationRetriever(gateway, stores.evidence, settings)
    return list(
        await retriever.retrieve(
            organization_id=context.organization_id,
            conversation_id=context.conversation_id,
            query=query,
            job_id=context.job_id,
            account_id=context.account_id,
            k=settings.retrieve_k,
        )
    )


async def generate_one_section(
    context: JobContext,
    section_number: str,
    expected_revision: int,
    scope: GenerationScope | None = None,
) -> str:
    """Draft one section. Return succeeded, skipped, or failed."""

    gateway = require_gateway(context)
    active = scope if scope is not None else BoundScope(generation_stores_from(context))
    if context.conversation_id is None:
        raise InvalidJobInputError
    settings = worker_settings()

    async with active.open() as stores:
        plan = await _plan_section(context, stores, section_number, expected_revision)
    if plan.outcome is not None:
        return plan.outcome
    record = plan.record
    if record is None:
        raise WorkerServiceError

    try:
        async with active.open() as stores:
            retrieved = await _retrieve(context, gateway, stores, settings, plan.query)
        messages = section_generation_messages(
            section_number=record.section_number,
            title=record.title,
            instructions=record.instructions,
            trial_passages=_trial_passages(retrieved),
            evidence=retrieved,
            memory=list(plan.memory),
        )
        prompt = "\n\n".join(message.content for message in messages)
        completed = await gateway.complete(
            ChatRequest(
                messages=messages,
                model=settings.chat_model,
                organization_id=context.organization_id,
                conversation_id=context.conversation_id,
                job_id=context.job_id,
                account_id=context.account_id,
                idempotency_key=(
                    f"{context.job_id}:{context.attempt}:generate:{section_number}"
                ),
                thinking=False,
            )
        )
    except _PROVIDER_ERRORS:
        async with active.open() as stores:
            await _record(
                context,
                stores.attempts,
                section_number,
                _FAILED,
                error_code=GenerationErrorCode.PROVIDER_FAILED.value,
            )
        return _FAILED

    cleaned = apply_citations(completed.text, {chunk.id for chunk in retrieved}).strip()
    if not cleaned:
        async with active.open() as stores:
            await _record(
                context,
                stores.attempts,
                section_number,
                _FAILED,
                model=completed.model,
                prompt=prompt,
                error_code=GenerationErrorCode.EMPTY_OUTPUT.value,
            )
        return _FAILED

    async with active.open() as stores:
        saved = await stores.sections.revise_draft(
            context.organization_id,
            context.conversation_id,
            section_number,
            expected_revision=expected_revision,
            content=cleaned,
            author_account_id=context.account_id,
            now=datetime.now(UTC),
            action=M11_REVISION_ACTION_GENERATED,
        )
        if not saved:
            await _record(
                context,
                stores.attempts,
                section_number,
                _FAILED,
                model=completed.model,
                prompt=prompt,
                content=cleaned,
                error_code=GenerationErrorCode.REVISION_CONFLICT.value,
            )
            return _FAILED
        await _record(
            context,
            stores.attempts,
            section_number,
            _SUCCEEDED,
            model=completed.model,
            prompt=prompt,
            content=cleaned,
            citation_ids=[str(chunk_id) for chunk_id in parse_cite_ids(cleaned)],
        )
    return _SUCCEEDED


def _selection_slice(
    content: str,
    start: int | None,
    end: int | None,
) -> tuple[str | None, str]:
    if start is None or end is None:
        return None, content
    if not 0 <= start < end <= len(content):
        raise ValueError
    return content[start:end], content


def _apply_rewrite(
    original: str,
    rewritten: str,
    start: int | None,
    end: int | None,
    allowed: set,
    keep_citations: bool,
) -> str:
    cite_allowed = allowed if keep_citations else set()
    cleaned = apply_citations(rewritten, cite_allowed).strip()
    if start is None or end is None:
        return cleaned
    return original[:start] + cleaned + original[end:]


async def rewrite_one_section(
    context: JobContext,
    request: RewriteRequest,
    scope: GenerationScope | None = None,
) -> str:
    """Propose two rewrite options without saving the section."""

    gateway = require_gateway(context)
    active = scope if scope is not None else BoundScope(generation_stores_from(context))
    if context.conversation_id is None:
        raise InvalidJobInputError
    settings = worker_settings()

    async with active.open() as stores:
        plan = await _plan_section(
            context,
            stores,
            request.section_number,
            request.expected_revision,
        )
    if plan.outcome is not None:
        return plan.outcome
    record = plan.record
    if record is None:
        raise WorkerServiceError

    try:
        selected, _ = _selection_slice(
            record.content,
            request.selection_start,
            request.selection_end,
        )
    except ValueError:
        async with active.open() as stores:
            await _record(
                context,
                stores.attempts,
                request.section_number,
                _FAILED,
                error_code=GenerationErrorCode.INVALID_SELECTION.value,
            )
        return _FAILED

    await context.check_cancelled()
    retrieved: list[EvidenceChunk] = []
    if request.use_sources:
        await context.check_cancelled()
        try:
            async with active.open() as stores:
                retrieved = await _retrieve(
                    context,
                    gateway,
                    stores,
                    settings,
                    plan.query,
                )
        except _PROVIDER_ERRORS:
            async with active.open() as stores:
                await _record(
                    context,
                    stores.attempts,
                    request.section_number,
                    _FAILED,
                    error_code=GenerationErrorCode.PROVIDER_FAILED.value,
                )
            return _FAILED

    allowed = {chunk.id for chunk in retrieved} if request.use_sources else set()
    options: list[dict[str, str]] = []
    prompts: list[str] = []
    cited: list[str] = []
    model: str | None = None
    for index, hint in enumerate(REWRITE_VARIANT_HINTS[:REWRITE_ALTERNATIVE_COUNT]):
        messages = section_rewrite_messages(
            section_number=record.section_number,
            title=record.title,
            instructions=record.instructions,
            trial_passages=_trial_passages(retrieved),
            evidence=retrieved,
            memory=list(plan.memory),
            current_content=record.content,
            selected_passage=selected,
            instruction=request.instruction,
            variant_hint=hint,
        )
        prompts.append("\n\n".join(message.content for message in messages))
        await context.check_cancelled()
        try:
            completed = await gateway.complete(
                ChatRequest(
                    messages=messages,
                    model=settings.chat_model,
                    organization_id=context.organization_id,
                    conversation_id=context.conversation_id,
                    job_id=context.job_id,
                    account_id=context.account_id,
                    idempotency_key=(
                        f"{context.job_id}:{context.attempt}:rewrite:"
                        f"{request.section_number}:{index}"
                    ),
                    thinking=False,
                )
            )
        except _PROVIDER_ERRORS:
            async with active.open() as stores:
                await _record(
                    context,
                    stores.attempts,
                    request.section_number,
                    _FAILED,
                    prompt="\n\n---\n\n".join(prompts),
                    error_code=GenerationErrorCode.PROVIDER_FAILED.value,
                )
            return _FAILED
        model = completed.model
        full = _apply_rewrite(
            record.content,
            completed.text,
            request.selection_start,
            request.selection_end,
            allowed,
            request.keep_citations,
        ).strip()
        if not full:
            async with active.open() as stores:
                await _record(
                    context,
                    stores.attempts,
                    request.section_number,
                    _FAILED,
                    model=model,
                    prompt="\n\n---\n\n".join(prompts),
                    error_code=GenerationErrorCode.EMPTY_OUTPUT.value,
                )
            return _FAILED
        options.append({"id": f"alternative-{index + 1}", "text": full})
        cited.extend(str(chunk_id) for chunk_id in parse_cite_ids(full))

    async with active.open() as stores:
        await _record(
            context,
            stores.attempts,
            request.section_number,
            _SUCCEEDED,
            model=model,
            prompt="\n\n---\n\n".join(prompts),
            content=json.dumps({"kind": REWRITE_OPTIONS_KIND, "items": options}),
            citation_ids=list(dict.fromkeys(cited)),
        )
    return _SUCCEEDED


async def generate_sections_pipeline(
    context: JobContext,
    scope: GenerationScope | None = None,
) -> None:
    """Draft every requested section that still matches its expected revision.

    Sections succeed or fail independently: one failure never discards a draft
    that already landed, and the job still ends failed so the caller can retry
    only what is still empty.
    """

    require_gateway(context)
    active = scope if scope is not None else BoundScope(generation_stores_from(context))
    if context.conversation_id is None:
        raise InvalidJobInputError

    if _job_mode(context.parameters) == GENERATE_MODE_REWRITE:
        request = parse_rewrite_request(context.parameters)
        await context.report(_START_PERCENT)
        await context.check_cancelled()
        if await rewrite_one_section(context, request, active) == _FAILED:
            raise GenerateSectionError
        await context.report(_DONE_PERCENT)
        return

    requested = parse_generate_request(context.parameters)
    failed = False
    total = len(requested)
    await context.report(_START_PERCENT)
    for index, (section_number, expected_revision) in enumerate(requested):
        await context.check_cancelled()
        outcome = await generate_one_section(
            context,
            section_number,
            expected_revision,
            active,
        )
        if outcome == _FAILED:
            failed = True
        if total:
            await context.report(
                _START_PERCENT + int(_WORK_PERCENT * (index + 1) / total)
            )
    if failed:
        raise GenerateSectionError
    await context.report(_DONE_PERCENT)


async def run_generate_sections_job(
    context: JobContext,
    runtime: DatabaseRuntime,
    chroma_index: ChromaIndex,
) -> None:
    """Run the drafting pipeline against the database, one transaction per step."""

    require_gateway(context)
    await generate_sections_pipeline(
        context,
        TransactionScope(runtime, chroma_index, context),
    )

