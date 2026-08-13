"""Read and write provider_calls without trusting row counts (bug B23)."""

from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from trialscribe_db.runtime import DatabaseRuntime

from trialscribe_worker.models.provider_call import ProviderCall
from trialscribe_worker.providers.gateway import ProviderCallRecord
from trialscribe_worker.utils.enum import ProviderOutcome


class ProviderCallRepository:
    """Persist metered provider attempts in the caller's transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find(self, idempotency_key: str) -> ProviderCall | None:
        """Return the succeeded row for this key, otherwise the earliest row."""

        succeeded = (
            select(ProviderCall)
            .where(
                ProviderCall.idempotency_key == idempotency_key,
                ProviderCall.outcome == ProviderOutcome.SUCCEEDED.value,
            )
            .order_by(ProviderCall.created_at, ProviderCall.id)
            .limit(1)
        )
        row = (await self._session.execute(succeeded)).scalars().first()
        if row is not None:
            return row
        statement = (
            select(ProviderCall)
            .where(ProviderCall.idempotency_key == idempotency_key)
            .order_by(ProviderCall.created_at, ProviderCall.id)
            .limit(1)
        )
        return (await self._session.execute(statement)).scalars().first()

    async def insert(self, row: ProviderCall) -> ProviderCall:
        """Insert a call, or return the existing succeeded row for this key."""

        statement = (
            insert(ProviderCall.__table__)
            .values(
                id=row.id,
                organization_id=row.organization_id,
                conversation_id=row.conversation_id,
                job_id=row.job_id,
                account_id=row.account_id,
                idempotency_key=row.idempotency_key,
                provider=row.provider,
                operation=row.operation,
                model=row.model,
                pricing_version=row.pricing_version,
                input_tokens=row.input_tokens,
                output_tokens=row.output_tokens,
                cache_hit_tokens=row.cache_hit_tokens,
                cost_micros=row.cost_micros,
                latency_ms=row.latency_ms,
                outcome=row.outcome,
            )
            .on_conflict_do_nothing(
                index_elements=["idempotency_key"],
                index_where=text("outcome = 'succeeded'"),
            )
            .returning(ProviderCall.__table__.c.id)
        )
        inserted = (await self._session.execute(statement)).scalar_one_or_none()
        if inserted is None:
            existing = await self.find(row.idempotency_key)
            if existing is None:
                raise RuntimeError("provider call insert lost the row")
            return existing
        loaded = await self.find_by_id(inserted)
        if loaded is None:
            raise RuntimeError("provider call insert lost the row")
        return loaded

    async def find_by_id(self, call_id: UUID) -> ProviderCall | None:
        statement = select(ProviderCall).where(ProviderCall.id == call_id)
        return (await self._session.execute(statement)).scalars().first()

    async def list_for_job(
        self,
        organization_id: UUID,
        job_id: UUID,
    ) -> list[ProviderCall]:
        """List a job's calls in the order they happened."""

        statement = (
            select(ProviderCall)
            .where(
                ProviderCall.organization_id == organization_id,
                ProviderCall.job_id == job_id,
            )
            .order_by(ProviderCall.created_at, ProviderCall.id)
        )
        return list((await self._session.execute(statement)).scalars().all())


class PostgresUsageRecorder:
    """UsageRecorder that writes each attempt in its own short transaction."""

    def __init__(self, runtime: DatabaseRuntime) -> None:
        self._runtime = runtime

    async def find(self, idempotency_key: str) -> ProviderCallRecord | None:
        async with self._runtime.transaction() as session:
            row = await ProviderCallRepository(session).find(idempotency_key)
            return None if row is None else _to_record(row)

    async def record(self, record: ProviderCallRecord) -> None:
        async with self._runtime.transaction() as session:
            await ProviderCallRepository(session).insert(_from_record(record))


def _from_record(record: ProviderCallRecord) -> ProviderCall:
    return ProviderCall(
        id=uuid4(),
        organization_id=record.organization_id,
        conversation_id=record.conversation_id,
        job_id=record.job_id,
        account_id=record.account_id,
        idempotency_key=record.idempotency_key,
        provider=record.provider,
        operation=record.operation,
        model=record.model,
        pricing_version=record.pricing_version,
        input_tokens=record.input_tokens,
        output_tokens=record.output_tokens,
        cache_hit_tokens=record.cache_hit_tokens,
        cost_micros=record.cost_micros,
        latency_ms=record.latency_ms,
        outcome=record.outcome,
    )


def _to_record(row: ProviderCall) -> ProviderCallRecord:
    return ProviderCallRecord(
        idempotency_key=row.idempotency_key,
        organization_id=row.organization_id,
        conversation_id=row.conversation_id,
        job_id=row.job_id,
        account_id=row.account_id,
        provider=row.provider,
        operation=row.operation,
        model=row.model,
        pricing_version=row.pricing_version,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        cache_hit_tokens=row.cache_hit_tokens,
        cost_micros=row.cost_micros,
        latency_ms=row.latency_ms,
        outcome=row.outcome,
    )
