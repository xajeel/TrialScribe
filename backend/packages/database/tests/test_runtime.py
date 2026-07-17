import asyncio
from collections.abc import Callable
from typing import Any

import pytest

import trialscribe_db.runtime as runtime_module
from trialscribe_db.config import DatabaseSettings
from trialscribe_db.runtime import DatabaseRuntime


class FakeSession:
    def __init__(self) -> None:
        self.commit_calls = 0
        self.rollback_calls = 0
        self.close_calls = 0

    async def commit(self) -> None:
        self.commit_calls += 1

    async def rollback(self) -> None:
        self.rollback_calls += 1

    async def close(self) -> None:
        self.close_calls += 1


class FakeEngine:
    def __init__(self) -> None:
        self.sync_engine = object()
        self.dispose_calls = 0

    async def dispose(self) -> None:
        self.dispose_calls += 1


def make_runtime(session: FakeSession) -> tuple[DatabaseRuntime, FakeEngine]:
    engine = FakeEngine()
    runtime = DatabaseRuntime(engine=engine, session_factory=lambda: session)  # type: ignore[arg-type]
    return runtime, engine


def test_transaction_commits_and_closes() -> None:
    session = FakeSession()
    runtime, _engine = make_runtime(session)

    async def exercise() -> None:
        async with runtime.transaction() as yielded:
            assert yielded is session

    asyncio.run(exercise())

    assert session.commit_calls == 1
    assert session.rollback_calls == 0
    assert session.close_calls == 1


def test_transaction_rolls_back_and_closes_on_error() -> None:
    session = FakeSession()
    runtime, _engine = make_runtime(session)

    async def exercise() -> None:
        with pytest.raises(RuntimeError, match="cancel work"):
            async with runtime.transaction():
                raise RuntimeError("cancel work")

    asyncio.run(exercise())

    assert session.commit_calls == 0
    assert session.rollback_calls == 1
    assert session.close_calls == 1


def test_dispose_releases_engine() -> None:
    runtime, engine = make_runtime(FakeSession())

    asyncio.run(runtime.dispose())

    assert engine.dispose_calls == 1


def test_runtime_construction_and_vector_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = FakeEngine()
    engine_arguments: dict[str, Any] = {}
    listener_arguments: list[tuple[object, str, Callable[..., None]]] = []

    def fake_create_async_engine(url: str, **kwargs: Any) -> FakeEngine:
        engine_arguments.update(url=url, **kwargs)
        return engine

    def fake_listen(
        target: object,
        event_name: str,
        listener: Callable[..., None],
    ) -> None:
        listener_arguments.append((target, event_name, listener))

    monkeypatch.setattr(runtime_module, "create_async_engine", fake_create_async_engine)
    monkeypatch.setattr(runtime_module.event, "listen", fake_listen)
    settings = DatabaseSettings(
        database_url="postgresql+psycopg://trialscribe:secret@localhost/trialscribe"
    )

    runtime = runtime_module.create_database_runtime(settings)

    assert runtime.engine is engine
    assert engine_arguments == {
        "url": settings.connection_url(),
        "pool_pre_ping": True,
    }
    assert listener_arguments == [(engine.sync_engine, "connect", runtime_module._register_vector)]


def test_vector_registration_uses_async_psycopg_adapter() -> None:
    callback: Callable[..., Any] | None = None

    class FakeConnection:
        def run_async(self, registered_callback: Callable[..., Any]) -> None:
            nonlocal callback
            callback = registered_callback

    runtime_module._register_vector(FakeConnection(), object())

    assert callback is runtime_module.register_vector_async
