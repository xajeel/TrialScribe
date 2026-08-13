import asyncio
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.dialects import postgresql

from trialscribe_worker.models.provider_call import ProviderCall
from trialscribe_worker.repositories.provider_calls import ProviderCallRepository
from trialscribe_worker.utils.enum import ProviderOperation, ProviderOutcome

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000401")
JOB_ID = UUID("00000000-0000-4000-8000-000000000402")


class RecordingSession:
    def __init__(self) -> None:
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> Any:
        self.statements.append(statement)
        raise _Captured


class _Captured(Exception):
    pass


def compiled(statement: Any) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


def capture_insert() -> str:
    session = RecordingSession()
    repository = ProviderCallRepository(session)  # type: ignore[arg-type]
    row = ProviderCall(
        id=uuid4(),
        organization_id=ORGANIZATION_ID,
        conversation_id=None,
        job_id=JOB_ID,
        account_id=None,
        idempotency_key="job:1:chat:0",
        provider="fake",
        operation=ProviderOperation.CHAT.value,
        model="fake-chat",
        pricing_version="2026-08-13",
        input_tokens=10,
        output_tokens=5,
        cache_hit_tokens=0,
        cost_micros=2,
        latency_ms=3,
        outcome=ProviderOutcome.SUCCEEDED.value,
    )
    try:
        asyncio.run(repository.insert(row))
    except _Captured:
        pass
    return compiled(session.statements[0])


def test_insert_uses_on_conflict_and_returning() -> None:
    sql = capture_insert()
    assert "ON CONFLICT" in sql
    assert "RETURNING" in sql
    assert "idempotency_key" in sql


def test_find_and_list_statements_are_tenant_scoped() -> None:
    session = RecordingSession()
    repository = ProviderCallRepository(session)  # type: ignore[arg-type]
    try:
        asyncio.run(repository.list_for_job(ORGANIZATION_ID, JOB_ID))
    except _Captured:
        pass
    sql = compiled(session.statements[0])
    assert "organization_id" in sql
    assert "job_id" in sql
    assert "ORDER BY" in sql
