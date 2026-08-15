"""Assemble the stable-prefix prompt for one M11 section draft."""

from uuid import UUID

from trialscribe_worker.providers.types import ChatMessage
from trialscribe_worker.utils.constant import (
    GENERATE_EVIDENCE_CHARS,
    GENERATE_MEMORY_TURN_CHARS,
    GENERATE_MEMORY_TURN_LIMIT,
    GENERATE_SYSTEM_PROMPT,
)


def section_generation_messages(
    *,
    section_number: str,
    title: str,
    instructions: str,
    trial_passages: list[str],
    evidence: list[object],
    memory: list[tuple[str, str]],
) -> list[ChatMessage]:
    """Return chat messages: system, section spec, trial, evidence, instruction."""

    return [
        ChatMessage(role="system", content=GENERATE_SYSTEM_PROMPT),
        ChatMessage(
            role="user",
            content=_section_spec(section_number, title),
        ),
        ChatMessage(role="user", content=_trial_summary(trial_passages)),
        ChatMessage(role="user", content=_evidence_block(evidence)),
        ChatMessage(
            role="user",
            content=_instruction_block(instructions, memory),
        ),
    ]


def _section_spec(section_number: str, title: str) -> str:
    return f"Section spec\nnumber={section_number}\ntitle={title}"


def _trial_summary(trial_passages: list[str]) -> str:
    body = "\n\n".join(passage.strip() for passage in trial_passages if passage.strip())
    if not body:
        body = "(none)"
    return f"Trial summary\n{body}"


def _evidence_block(evidence: list[object]) -> str:
    lines = ["Evidence"]
    used = len(lines[0])
    for chunk in evidence:
        chunk_id = getattr(chunk, "id")
        page = getattr(chunk, "page_number")
        entry = (
            f"id={_uuid_text(chunk_id)} kind={getattr(chunk, 'source_kind')} "
            f"identity={getattr(chunk, 'source_identity')} page={page} "
            f"span={getattr(chunk, 'start_char')}-{getattr(chunk, 'end_char')}\n"
            f"{getattr(chunk, 'text')}"
        )
        extra = 2 + len(entry)
        if used + extra > GENERATE_EVIDENCE_CHARS and len(lines) > 1:
            break
        lines.append(entry)
        used += extra
    if len(lines) == 1:
        lines.append("(none)")
    return "\n\n".join(lines)


def _instruction_block(instructions: str, memory: list[tuple[str, str]]) -> str:
    standing = instructions.strip() or "(none)"
    turns = memory[-GENERATE_MEMORY_TURN_LIMIT:]
    clipped: list[str] = []
    for role, text in turns:
        body = text.strip()[:GENERATE_MEMORY_TURN_CHARS]
        clipped.append(f"{role}: {body}")
    memory_block = "\n".join(clipped) if clipped else "(none)"
    return f"Instruction\n{standing}\n\nConversation\n{memory_block}"


def _uuid_text(value: object) -> str:
    if isinstance(value, UUID):
        return str(value)
    return str(value)
