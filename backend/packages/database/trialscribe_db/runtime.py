"""Asynchronous PostgreSQL transaction runtime."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from pgvector.psycopg import register_vector_async
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from trialscribe_db.config import DatabaseSettings


def _register_vector(dbapi_connection: Any, _connection_record: Any) -> None:
    """Register pgvector codecs on a Psycopg async connection."""

    dbapi_connection.run_async(register_vector_async)


@dataclass(slots=True)
class DatabaseRuntime:
    """Own an engine and create an isolated session for each transaction."""

    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        session = self.session_factory()
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def dispose(self) -> None:
        """Release all pooled database connections."""

        await self.engine.dispose()


def create_database_runtime(settings: DatabaseSettings) -> DatabaseRuntime:
    """Build a database runtime from validated settings."""

    engine = create_async_engine(settings.connection_url(), pool_pre_ping=True)
    event.listen(engine.sync_engine, "connect", _register_vector)
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return DatabaseRuntime(engine=engine, session_factory=session_factory)
