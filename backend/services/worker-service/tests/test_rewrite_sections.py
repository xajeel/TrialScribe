import asyncio
import importlib.util
import json
from pathlib import Path
from uuid import UUID

import pytest

from trialscribe_worker.pipelines.generate_sections import (
    generate_sections_pipeline,
    parse_generate_request,
    parse_rewrite_request,
)
from trialscribe_worker.utils.constant import (
    GENERATE_EXPECTED_REVISIONS_PARAMETER,
    GENERATE_MODE_PARAMETER,
    GENERATE_MODE_REWRITE,
    GENERATE_SECTIONS_PARAMETER,
    M11_SECTION_DONE_STATUS,
    REWRITE_INSTRUCTION_PARAMETER,
    REWRITE_KEEP_CITATIONS_PARAMETER,
    REWRITE_OPTIONS_KIND,
    REWRITE_SELECTION_END_PARAMETER,
    REWRITE_SELECTION_START_PARAMETER,
    REWRITE_USE_SOURCES_PARAMETER,
)
from trialscribe_worker.utils.exceptions import (
    GenerateSectionError,
    InvalidJobInputError,
)

_HELPERS = importlib.util.spec_from_file_location(
    "generate_sections_rewrite_helpers",
    Path(__file__).with_name("test_generate_sections.py"),
)
assert _HELPERS is not None and _HELPERS.loader is not None
_generate = importlib.util.module_from_spec(_HELPERS)
_HELPERS.loader.exec_module(_generate)
CitingChat = _generate.CitingChat
MARKER = _generate.MARKER
MemoryAttempts = _generate.MemoryAttempts
MemorySections = _generate.MemorySections
_context = _generate._context
_evidence = _generate._evidence
_gateway = _generate._gateway
_section = _generate._section
_seed_trial = _generate._seed_trial

ORIGINAL = "PREFIX selected passage SUFFIX"


def _rewrite_parameters(
    *,
    instruction: str = "Make it clearer.",
    start: int | None = None,
    end: int | None = None,
    keep_citations: bool = True,
    use_sources: bool = True,
    numbers: list[str] | None = None,
    expected: dict[str, int] | None = None,
) -> dict[str, object]:
    parameters: dict[str, object] = {
        GENERATE_MODE_PARAMETER: GENERATE_MODE_REWRITE,
        GENERATE_SECTIONS_PARAMETER: numbers or ["5"],
        GENERATE_EXPECTED_REVISIONS_PARAMETER: expected or {"5": 0},
        REWRITE_INSTRUCTION_PARAMETER: instruction,
        REWRITE_KEEP_CITATIONS_PARAMETER: keep_citations,
        REWRITE_USE_SOURCES_PARAMETER: use_sources,
    }
    if start is not None and end is not None:
        parameters[REWRITE_SELECTION_START_PARAMETER] = start
        parameters[REWRITE_SELECTION_END_PARAMETER] = end
    return parameters


def test_generate_request_without_mode_still_lists_sections() -> None:
    pairs = parse_generate_request(
        {
            GENERATE_SECTIONS_PARAMETER: ["5"],
            GENERATE_EXPECTED_REVISIONS_PARAMETER: {"5": 0},
        }
    )
    assert pairs == [("5", 0)]


def test_rewrite_request_requires_one_section_and_an_instruction() -> None:
    request = parse_rewrite_request(_rewrite_parameters())
    assert request.section_number == "5"
    assert request.instruction == "Make it clearer."
    with pytest.raises(InvalidJobInputError):
        parse_rewrite_request(
            _rewrite_parameters(numbers=["5", "4"], expected={"5": 0, "4": 0})
        )
    with pytest.raises(InvalidJobInputError):
        parse_rewrite_request(_rewrite_parameters(instruction="   "))


def test_rewrite_does_not_change_section_content() -> None:
    evidence = _evidence()
    asyncio.run(_seed_trial(evidence, MARKER))
    sections = MemorySections(
        {"5": _section("5", "TRIAL POPULATION", content=ORIGINAL)}
    )
    attempts = MemoryAttempts()
    context = _context(
        evidence=evidence,
        gateway=_gateway(CitingChat()),
        sections=sections,
        attempts=attempts,
    )
    context.parameters = _rewrite_parameters()
    asyncio.run(generate_sections_pipeline(context))
    assert sections.rows["5"].content == ORIGINAL
    assert sections.rows["5"].current_revision == 0
    payload = json.loads(str(attempts.rows[-1]["content"]))
    assert payload["kind"] == REWRITE_OPTIONS_KIND
    assert [item["id"] for item in payload["items"]] == [
        "alternative-1",
        "alternative-2",
    ]
    assert MARKER in payload["items"][0]["text"]


def test_done_section_rewrite_is_skipped() -> None:
    evidence = _evidence()
    asyncio.run(_seed_trial(evidence, MARKER))
    sections = MemorySections(
        {
            "5": _section(
                "5",
                "TRIAL POPULATION",
                status=M11_SECTION_DONE_STATUS,
                content="keep me",
            )
        }
    )
    attempts = MemoryAttempts()
    context = _context(
        evidence=evidence,
        gateway=_gateway(CitingChat()),
        sections=sections,
        attempts=attempts,
    )
    context.parameters = _rewrite_parameters()
    asyncio.run(generate_sections_pipeline(context))
    assert sections.rows["5"].content == "keep me"
    assert attempts.rows[-1]["status"] == "skipped"


def test_selection_splice_keeps_prefix_and_suffix() -> None:
    evidence = _evidence()
    chunk_id = asyncio.run(_seed_trial(evidence, MARKER))
    start = ORIGINAL.index("selected")
    end = start + len("selected passage")
    sections = MemorySections(
        {"5": _section("5", "TRIAL POPULATION", content=ORIGINAL)}
    )
    attempts = MemoryAttempts()
    context = _context(
        evidence=evidence,
        gateway=_gateway(CitingChat()),
        sections=sections,
        attempts=attempts,
    )
    context.parameters = _rewrite_parameters(start=start, end=end)
    asyncio.run(generate_sections_pipeline(context))
    text = json.loads(str(attempts.rows[-1]["content"]))["items"][0]["text"]
    assert text.startswith("PREFIX ")
    assert text.endswith(" SUFFIX")
    assert f"[cite:{chunk_id}]" in text
    assert sections.rows["5"].content == ORIGINAL


def test_unresolved_rewrite_citations_are_stripped() -> None:
    evidence = _evidence()
    asyncio.run(_seed_trial(evidence, MARKER))
    foreign = UUID("00000000-0000-4000-8000-000000000999")
    sections = MemorySections(
        {"5": _section("5", "TRIAL POPULATION", content=ORIGINAL)}
    )
    attempts = MemoryAttempts()
    context = _context(
        evidence=evidence,
        gateway=_gateway(CitingChat(extra_cite=foreign)),
        sections=sections,
        attempts=attempts,
    )
    context.parameters = _rewrite_parameters()
    asyncio.run(generate_sections_pipeline(context))
    text = json.loads(str(attempts.rows[-1]["content"]))["items"][0]["text"]
    assert f"[cite:{foreign}]" not in text


def test_invalid_selection_fails_without_saving() -> None:
    evidence = _evidence()
    asyncio.run(_seed_trial(evidence, MARKER))
    sections = MemorySections(
        {"5": _section("5", "TRIAL POPULATION", content=ORIGINAL)}
    )
    attempts = MemoryAttempts()
    context = _context(
        evidence=evidence,
        gateway=_gateway(CitingChat()),
        sections=sections,
        attempts=attempts,
    )
    context.parameters = _rewrite_parameters(start=0, end=len(ORIGINAL) + 8)
    with pytest.raises(GenerateSectionError):
        asyncio.run(generate_sections_pipeline(context))
    assert sections.rows["5"].content == ORIGINAL
    assert attempts.rows[-1]["error_code"] == "invalid_selection"
