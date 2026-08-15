"""Draft requested M11 sections from tenant-scoped evidence with citations."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace

from trialscribe_db.runtime import DatabaseRuntime

from trialscribe_worker.config import WorkerSettings
from trialscribe_worker.prompts.section_generation import (
    section_generation_messages,
    section_rewrite_messages,
)
from trialscribe_worker.providers.gateway import ProviderGateway
from trialscribe_worker.providers.types import ChatRequest
from trialscribe_worker.repositories.conversation_memory import ConversationMemoryStore
from trialscribe_worker.repositories.evidence_chunks import EvidenceChunkRepository
from trialscribe_worker.repositories.m11_sections import M11SectionStore
from trialscribe_worker.repositories.section_generation_attempts import (
    SectionGenerationAttemptRepository,
)
from trialscribe_worker.retrieval.chroma_index import ChromaIndex, EvidenceIndex
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


async def _record(
    context: JobContext,
    section_number: str,
    status: str,
    *,
    model: str | None = None,
    prompt: str | None = None,
    content: str | None = None,
    error_code: str | None = None,
    citation_ids: list[str] | None = None,
) -> None:
    attempts = getattr(context.generate, "attempts", None)
    add = getattr(attempts, "add", None)
    if not callable(add):
        raise WorkerServiceError
    if context.conversation_id is None:
        raise InvalidJobInputError
    await add(
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


async def generate_one_section(
    context: JobContext,
    section_number: str,
    expected_revision: int,
) -> str:
    """Draft one section. Return succeeded, skipped, or failed."""

    if context.gateway is None or context.evidence is None or context.generate is None:
        raise WorkerServiceError
    if not isinstance(context.gateway, ProviderGateway):
        raise WorkerServiceError
    if not isinstance(context.evidence, EvidenceIndex):
        raise WorkerServiceError
    if context.conversation_id is None:
        raise InvalidJobInputError
    sections = getattr(context.generate, "sections", None)
    memory_store = getattr(context.generate, "memory", None)
    get_scoped = getattr(sections, "get_scoped", None)
    revise_draft = getattr(sections, "revise_draft", None)
    recent = getattr(memory_store, "recent", None)
    if not callable(get_scoped) or not callable(revise_draft) or not callable(recent):
        raise WorkerServiceError
    conversation_id = context.conversation_id
    record = await get_scoped(
        context.organization_id,
        conversation_id,
        section_number,
    )
    if record is None:
        await _record(
            context,
            section_number,
            GenerationAttemptStatus.FAILED.value,
            error_code=GenerationErrorCode.MISSING_SECTION.value,
        )
        return GenerationAttemptStatus.FAILED.value
    if record.status == M11_SECTION_DONE_STATUS:
        await _record(
            context,
            section_number,
            GenerationAttemptStatus.SKIPPED.value,
        )
        return GenerationAttemptStatus.SKIPPED.value
    if record.current_revision != expected_revision:
        await _record(
            context,
            section_number,
            GenerationAttemptStatus.SKIPPED.value,
            error_code=GenerationErrorCode.REVISION_CONFLICT.value,
        )
        return GenerationAttemptStatus.SKIPPED.value
    settings = WorkerSettings()
    query = record.title
    if record.instructions.strip():
        query = f"{record.title}\n{record.instructions}"
    retriever = ConversationRetriever(context.gateway, context.evidence, settings)
    try:
        retrieved = await retriever.retrieve(
            organization_id=context.organization_id,
            conversation_id=conversation_id,
            query=query,
            job_id=context.job_id,
            account_id=context.account_id,
            k=settings.retrieve_k,
        )
        turns = await recent(
            context.organization_id,
            conversation_id,
            GENERATE_MEMORY_TURN_LIMIT,
        )
        trial_passages = [
            chunk.text
            for chunk in retrieved
            if chunk.source_kind == EVIDENCE_SOURCE_TRIAL_DATA
        ]
        messages = section_generation_messages(
            section_number=record.section_number,
            title=record.title,
            instructions=record.instructions,
            trial_passages=trial_passages,
            evidence=list(retrieved),
            memory=list(turns),
        )
        prompt = "\n\n".join(message.content for message in messages)
        completed = await context.gateway.complete(
            ChatRequest(
                messages=messages,
                model=settings.chat_model,
                organization_id=context.organization_id,
                conversation_id=conversation_id,
                job_id=context.job_id,
                account_id=context.account_id,
                idempotency_key=(
                    f"{context.job_id}:{context.attempt}:generate:{section_number}"
                ),
                thinking=False,
            )
        )
    except _PROVIDER_ERRORS:
        await _record(
            context,
            section_number,
            GenerationAttemptStatus.FAILED.value,
            error_code=GenerationErrorCode.PROVIDER_FAILED.value,
        )
        return GenerationAttemptStatus.FAILED.value
    allowed = {chunk.id for chunk in retrieved}
    cleaned = apply_citations(completed.text, allowed).strip()
    if not cleaned:
        await _record(
            context,
            section_number,
            GenerationAttemptStatus.FAILED.value,
            model=completed.model,
            prompt=prompt,
            error_code=GenerationErrorCode.EMPTY_OUTPUT.value,
        )
        return GenerationAttemptStatus.FAILED.value
    saved = await revise_draft(
        context.organization_id,
        conversation_id,
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
            section_number,
            GenerationAttemptStatus.FAILED.value,
            model=completed.model,
            prompt=prompt,
            content=cleaned,
            error_code=GenerationErrorCode.REVISION_CONFLICT.value,
        )
        return GenerationAttemptStatus.FAILED.value
    cited = [str(chunk_id) for chunk_id in parse_cite_ids(cleaned)]
    await _record(
        context,
        section_number,
        GenerationAttemptStatus.SUCCEEDED.value,
        model=completed.model,
        prompt=prompt,
        content=cleaned,
        citation_ids=cited,
    )
    return GenerationAttemptStatus.SUCCEEDED.value


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


async def rewrite_one_section(context: JobContext, request: RewriteRequest) -> str:
    """Propose two rewrite options without saving the section."""

    if context.gateway is None or context.evidence is None or context.generate is None:
        raise WorkerServiceError
    if not isinstance(context.gateway, ProviderGateway):
        raise WorkerServiceError
    if context.conversation_id is None:
        raise InvalidJobInputError
    sections = getattr(context.generate, "sections", None)
    memory_store = getattr(context.generate, "memory", None)
    get_scoped = getattr(sections, "get_scoped", None)
    recent = getattr(memory_store, "recent", None)
    if not callable(get_scoped) or not callable(recent):
        raise WorkerServiceError
    conversation_id = context.conversation_id
    record = await get_scoped(
        context.organization_id,
        conversation_id,
        request.section_number,
    )
    if record is None:
        await _record(
            context,
            request.section_number,
            GenerationAttemptStatus.FAILED.value,
            error_code=GenerationErrorCode.MISSING_SECTION.value,
        )
        return GenerationAttemptStatus.FAILED.value
    if record.status == M11_SECTION_DONE_STATUS:
        await _record(
            context,
            request.section_number,
            GenerationAttemptStatus.SKIPPED.value,
        )
        return GenerationAttemptStatus.SKIPPED.value
    if record.current_revision != request.expected_revision:
        await _record(
            context,
            request.section_number,
            GenerationAttemptStatus.SKIPPED.value,
            error_code=GenerationErrorCode.REVISION_CONFLICT.value,
        )
        return GenerationAttemptStatus.SKIPPED.value
    try:
        selected, _ = _selection_slice(
            record.content,
            request.selection_start,
            request.selection_end,
        )
    except ValueError:
        await _record(
            context,
            request.section_number,
            GenerationAttemptStatus.FAILED.value,
            error_code=GenerationErrorCode.INVALID_SELECTION.value,
        )
        return GenerationAttemptStatus.FAILED.value
    settings = WorkerSettings()
    retrieved: list[object] = []
    trial_passages: list[str] = []
    turns = await recent(
        context.organization_id,
        conversation_id,
        GENERATE_MEMORY_TURN_LIMIT,
    )
    if request.use_sources:
        if not isinstance(context.evidence, EvidenceIndex):
            raise WorkerServiceError
        query = record.title
        if record.instructions.strip():
            query = f"{record.title}\n{record.instructions}"
        retriever = ConversationRetriever(context.gateway, context.evidence, settings)
        try:
            retrieved = list(
                await retriever.retrieve(
                    organization_id=context.organization_id,
                    conversation_id=conversation_id,
                    query=query,
                    job_id=context.job_id,
                    account_id=context.account_id,
                    k=settings.retrieve_k,
                )
            )
        except _PROVIDER_ERRORS:
            await _record(
                context,
                request.section_number,
                GenerationAttemptStatus.FAILED.value,
                error_code=GenerationErrorCode.PROVIDER_FAILED.value,
            )
            return GenerationAttemptStatus.FAILED.value
        trial_passages = [
            chunk.text
            for chunk in retrieved
            if chunk.source_kind == EVIDENCE_SOURCE_TRIAL_DATA
        ]
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
            trial_passages=trial_passages,
            evidence=retrieved,
            memory=list(turns),
            current_content=record.content,
            selected_passage=selected,
            instruction=request.instruction,
            variant_hint=hint,
        )
        prompt = "\n\n".join(message.content for message in messages)
        prompts.append(prompt)
        try:
            completed = await context.gateway.complete(
                ChatRequest(
                    messages=messages,
                    model=settings.chat_model,
                    organization_id=context.organization_id,
                    conversation_id=conversation_id,
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
            await _record(
                context,
                request.section_number,
                GenerationAttemptStatus.FAILED.value,
                prompt="\n\n---\n\n".join(prompts),
                error_code=GenerationErrorCode.PROVIDER_FAILED.value,
            )
            return GenerationAttemptStatus.FAILED.value
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
            await _record(
                context,
                request.section_number,
                GenerationAttemptStatus.FAILED.value,
                model=model,
                prompt="\n\n---\n\n".join(prompts),
                error_code=GenerationErrorCode.EMPTY_OUTPUT.value,
            )
            return GenerationAttemptStatus.FAILED.value
        option_id = f"alternative-{index + 1}"
        options.append({"id": option_id, "text": full})
        cited.extend(str(chunk_id) for chunk_id in parse_cite_ids(full))
    unique_cites = list(dict.fromkeys(cited))
    await _record(
        context,
        request.section_number,
        GenerationAttemptStatus.SUCCEEDED.value,
        model=model,
        prompt="\n\n---\n\n".join(prompts),
        content=json.dumps({"kind": REWRITE_OPTIONS_KIND, "items": options}),
        citation_ids=unique_cites,
    )
    return GenerationAttemptStatus.SUCCEEDED.value


async def generate_sections_pipeline(context: JobContext) -> None:
    """Draft every requested section that still matches its expected revision."""

    if context.gateway is None or context.evidence is None or context.generate is None:
        raise WorkerServiceError
    if context.conversation_id is None:
        raise InvalidJobInputError
    if _job_mode(context.parameters) == GENERATE_MODE_REWRITE:
        request = parse_rewrite_request(context.parameters)
        await context.report(10)
        outcome = await rewrite_one_section(context, request)
        if outcome == GenerationAttemptStatus.FAILED.value:
            raise GenerateSectionError
        await context.report(100)
        return
    requested = parse_generate_request(context.parameters)
    failed = False
    total = len(requested)
    await context.report(10)
    for index, (section_number, expected_revision) in enumerate(requested):
        await context.check_cancelled()
        outcome = await generate_one_section(
            context,
            section_number,
            expected_revision,
        )
        if outcome == GenerationAttemptStatus.FAILED.value:
            failed = True
        if total:
            await context.report(10 + int(80 * (index + 1) / total))
    if failed:
        raise GenerateSectionError
    await context.report(100)


def bind_generate_stores(context: JobContext, session: object, chroma_index: ChromaIndex) -> None:
    """Attach tenant-scoped stores for one database session."""

    context.evidence = EvidenceIndex(EvidenceChunkRepository(session), chroma_index)  # type: ignore[arg-type]
    context.generate = SimpleNamespace(
        sections=M11SectionStore(session),  # type: ignore[arg-type]
        memory=ConversationMemoryStore(session),  # type: ignore[arg-type]
        attempts=SectionGenerationAttemptRepository(session),  # type: ignore[arg-type]
    )


async def run_generate_sections_job(
    context: JobContext,
    runtime: DatabaseRuntime,
    chroma_index: ChromaIndex,
) -> None:
    """Load, generate, and save each section without holding SQL across chat."""

    if not isinstance(context.gateway, ProviderGateway):
        raise WorkerServiceError
    if context.conversation_id is None:
        raise InvalidJobInputError
    if _job_mode(context.parameters) == GENERATE_MODE_REWRITE:
        request = parse_rewrite_request(context.parameters)
        await context.report(10)
        async with runtime.transaction() as session:
            bind_generate_stores(context, session, chroma_index)
            outcome = await rewrite_one_section(context, request)
        if outcome == GenerationAttemptStatus.FAILED.value:
            raise GenerateSectionError
        await context.report(100)
        return
    requested = parse_generate_request(context.parameters)
    failed = False
    total = len(requested)
    await context.report(10)
    for index, (section_number, expected_revision) in enumerate(requested):
        await context.check_cancelled()
        outcome = await _run_one_section_job(
            context,
            runtime,
            chroma_index,
            section_number,
            expected_revision,
        )
        if outcome == GenerationAttemptStatus.FAILED.value:
            failed = True
        if total:
            await context.report(10 + int(80 * (index + 1) / total))
    if failed:
        raise GenerateSectionError
    await context.report(100)


async def _run_one_section_job(
    context: JobContext,
    runtime: DatabaseRuntime,
    chroma_index: ChromaIndex,
    section_number: str,
    expected_revision: int,
) -> str:
    settings = WorkerSettings()
    async with runtime.transaction() as session:
        bind_generate_stores(context, session, chroma_index)
        record = await context.generate.sections.get_scoped(  # type: ignore[union-attr]
            context.organization_id,
            context.conversation_id,
            section_number,
        )
        if record is None:
            await _record(
                context,
                section_number,
                GenerationAttemptStatus.FAILED.value,
                error_code=GenerationErrorCode.MISSING_SECTION.value,
            )
            return GenerationAttemptStatus.FAILED.value
        if record.status == M11_SECTION_DONE_STATUS:
            await _record(
                context,
                section_number,
                GenerationAttemptStatus.SKIPPED.value,
            )
            return GenerationAttemptStatus.SKIPPED.value
        if record.current_revision != expected_revision:
            await _record(
                context,
                section_number,
                GenerationAttemptStatus.SKIPPED.value,
                error_code=GenerationErrorCode.REVISION_CONFLICT.value,
            )
            return GenerationAttemptStatus.SKIPPED.value
        turns = await context.generate.memory.recent(  # type: ignore[union-attr]
            context.organization_id,
            context.conversation_id,
            GENERATE_MEMORY_TURN_LIMIT,
        )
        query = record.title
        if record.instructions.strip():
            query = f"{record.title}\n{record.instructions}"
        title = record.title
        instructions = record.instructions
        loaded_number = record.section_number
    try:
        async with runtime.transaction() as session:
            bind_generate_stores(context, session, chroma_index)
            retriever = ConversationRetriever(
                context.gateway,
                context.evidence,  # type: ignore[arg-type]
                settings,
            )
            retrieved = await retriever.retrieve(
                organization_id=context.organization_id,
                conversation_id=context.conversation_id,
                query=query,
                job_id=context.job_id,
                account_id=context.account_id,
                k=settings.retrieve_k,
            )
        messages = section_generation_messages(
            section_number=loaded_number,
            title=title,
            instructions=instructions,
            trial_passages=[
                chunk.text
                for chunk in retrieved
                if chunk.source_kind == EVIDENCE_SOURCE_TRIAL_DATA
            ],
            evidence=list(retrieved),
            memory=list(turns),
        )
        prompt = "\n\n".join(message.content for message in messages)
        completed = await context.gateway.complete(
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
        async with runtime.transaction() as session:
            bind_generate_stores(context, session, chroma_index)
            await _record(
                context,
                section_number,
                GenerationAttemptStatus.FAILED.value,
                error_code=GenerationErrorCode.PROVIDER_FAILED.value,
            )
        return GenerationAttemptStatus.FAILED.value
    allowed = {chunk.id for chunk in retrieved}
    cleaned = apply_citations(completed.text, allowed).strip()
    if not cleaned:
        async with runtime.transaction() as session:
            bind_generate_stores(context, session, chroma_index)
            await _record(
                context,
                section_number,
                GenerationAttemptStatus.FAILED.value,
                model=completed.model,
                prompt=prompt,
                error_code=GenerationErrorCode.EMPTY_OUTPUT.value,
            )
        return GenerationAttemptStatus.FAILED.value
    async with runtime.transaction() as session:
        bind_generate_stores(context, session, chroma_index)
        saved = await context.generate.sections.revise_draft(  # type: ignore[union-attr]
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
                section_number,
                GenerationAttemptStatus.FAILED.value,
                model=completed.model,
                prompt=prompt,
                content=cleaned,
                error_code=GenerationErrorCode.REVISION_CONFLICT.value,
            )
            return GenerationAttemptStatus.FAILED.value
        await _record(
            context,
            section_number,
            GenerationAttemptStatus.SUCCEEDED.value,
            model=completed.model,
            prompt=prompt,
            content=cleaned,
            citation_ids=[str(chunk_id) for chunk_id in parse_cite_ids(cleaned)],
        )
    return GenerationAttemptStatus.SUCCEEDED.value
