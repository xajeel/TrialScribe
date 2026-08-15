from types import SimpleNamespace
from uuid import UUID

from trialscribe_worker.prompts.section_generation import section_generation_messages
from trialscribe_worker.utils.constant import GENERATE_MEMORY_TURN_LIMIT

CHUNK_ID = UUID("00000000-0000-4000-8000-000000000011")


def test_messages_start_with_untrusted_system_prompt() -> None:
    messages = section_generation_messages(
        section_number="5",
        title="TRIAL POPULATION",
        instructions="Include adults.",
        trial_passages=["Age 18+"],
        evidence=[],
        memory=[],
    )
    assert messages[0].role == "system"
    assert "untrusted" in messages[0].content.lower()
    assert messages[1].role == "user"
    assert "5" in messages[1].content
    assert "TRIAL POPULATION" in messages[1].content


def test_evidence_ids_appear_after_the_system_message() -> None:
    chunk = SimpleNamespace(
        id=CHUNK_ID,
        source_kind="trial_data",
        source_identity="trial-1",
        page_number=None,
        start_char=0,
        end_char=12,
        text="Age 18 years",
    )
    messages = section_generation_messages(
        section_number="5",
        title="TRIAL POPULATION",
        instructions="",
        trial_passages=[],
        evidence=[chunk],
        memory=[],
    )
    assert str(CHUNK_ID) not in messages[0].content
    evidence_text = messages[3].content
    assert f"id={CHUNK_ID}" in evidence_text
    assert "Age 18 years" in evidence_text


def test_memory_keeps_the_last_eight_turns() -> None:
    memory = [(("user" if index % 2 == 0 else "assistant"), f"turn-{index}") for index in range(12)]
    messages = section_generation_messages(
        section_number="5",
        title="TRIAL POPULATION",
        instructions="Adults only",
        trial_passages=[],
        evidence=[],
        memory=memory,
    )
    instruction = messages[4].content
    assert "turn-0" not in instruction
    assert "turn-3" not in instruction
    assert "turn-4" in instruction
    assert "turn-11" in instruction
    assert instruction.count("turn-") == GENERATE_MEMORY_TURN_LIMIT
