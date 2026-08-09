import asyncio
import os
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from pgvector.sqlalchemy import VECTOR
from sqlalchemy import String, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Mapped, mapped_column

from trialscribe_db.base import (
    Base,
    OrganizationScopedMixin,
    TimestampMixin,
    UuidPrimaryKeyMixin,
)
from trialscribe_db.config import DatabaseSettings
from trialscribe_db.runtime import create_database_runtime

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("TRIALSCRIBE_DATABASE_INTEGRATION") != "1",
        reason="requires the isolated PostgreSQL test project",
    ),
]

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PHASE = os.getenv("TRIALSCRIBE_DATABASE_PHASE")
RECORD_ID = UUID("00000000-0000-4000-8000-000000000001")
ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000002")
ROLLED_BACK_ID = UUID("00000000-0000-4000-8000-000000000003")
EMBEDDING = [0.125, 0.25, 0.5]


class FoundationIntegrationRecord(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    OrganizationScopedMixin,
    Base,
):
    __tablename__ = "foundation_integration_records"

    label: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(VECTOR(3), nullable=False)


def alembic_config() -> Config:
    return Config(PACKAGE_ROOT / "alembic.ini")


async def assert_current_capabilities(settings: DatabaseSettings) -> None:
    runtime = create_database_runtime(settings)
    try:
        async with runtime.transaction() as session:
            revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
            schema_exists = await session.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM pg_namespace "
                    "WHERE nspname = 'trialscribe')"
                )
            )
            vector_version = await session.scalar(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            )
        assert revision == "0009_processed_events"
        assert schema_exists is True
        assert vector_version is not None
    finally:
        await runtime.dispose()


async def prepare_persistent_record(settings: DatabaseSettings) -> None:
    runtime = create_database_runtime(settings)
    try:
        async with runtime.engine.begin() as connection:
            await connection.run_sync(
                lambda sync_connection: FoundationIntegrationRecord.__table__.create(
                    sync_connection,
                    checkfirst=True,
                )
            )

        async with runtime.transaction() as session:
            session.add(
                FoundationIntegrationRecord(
                    id=RECORD_ID,
                    organization_id=ORGANIZATION_ID,
                    label="committed",
                    embedding=EMBEDDING,
                )
            )

        with pytest.raises(RuntimeError, match="force rollback"):
            async with runtime.transaction() as session:
                session.add(
                    FoundationIntegrationRecord(
                        id=ROLLED_BACK_ID,
                        organization_id=ORGANIZATION_ID,
                        label="rolled-back",
                        embedding=EMBEDDING,
                    )
                )
                await session.flush()
                raise RuntimeError("force rollback")

        async with runtime.transaction() as session:
            record_ids = list(
                await session.scalars(
                    select(FoundationIntegrationRecord.id).order_by(
                        FoundationIntegrationRecord.id
                    )
                )
            )
        assert record_ids == [RECORD_ID]
    finally:
        await runtime.dispose()


async def assert_persistent_record(settings: DatabaseSettings) -> None:
    runtime = create_database_runtime(settings)
    try:
        async with runtime.transaction() as session:
            records = list(await session.scalars(select(FoundationIntegrationRecord)))
        assert len(records) == 1
        assert records[0].id == RECORD_ID
        assert records[0].organization_id == ORGANIZATION_ID
        assert list(records[0].embedding) == pytest.approx(EMBEDDING)
    finally:
        await runtime.dispose()


async def assert_runtime_error_redacts_password(url: str, password: str) -> None:
    failed_runtime = create_database_runtime(DatabaseSettings(database_url=url))
    try:
        with pytest.raises(Exception) as error:
            async with failed_runtime.transaction() as session:
                await session.execute(text("SELECT 1"))
        assert password not in str(error.value)
    finally:
        await failed_runtime.dispose()


@pytest.mark.skipif(PHASE != "prepare", reason="prepare phase only")
def test_prepare_database_and_persistent_record(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = DatabaseSettings()
    config = alembic_config()

    command.upgrade(config, "head")
    command.upgrade(config, "head")
    command.downgrade(config, "0001")
    command.upgrade(config, "head")
    asyncio.run(assert_current_capabilities(settings))
    asyncio.run(prepare_persistent_record(settings))

    parsed_url = make_url(settings.connection_url())
    password = parsed_url.password or ""
    failed_url = parsed_url.set(port=1).render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", failed_url)
    with pytest.raises(Exception) as migration_error:
        command.current(config)
    assert password not in str(migration_error.value)
    asyncio.run(assert_runtime_error_redacts_password(failed_url, password))


@pytest.mark.skipif(PHASE != "verify", reason="post-restart phase only")
def test_committed_vector_record_survives_restart() -> None:
    settings = DatabaseSettings()

    asyncio.run(assert_current_capabilities(settings))
    asyncio.run(assert_persistent_record(settings))
