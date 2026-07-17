import pytest
from pydantic import ValidationError

from trialscribe_db.config import DatabaseSettings


def test_loads_valid_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = "postgresql+psycopg://trialscribe:local-password@localhost:5432/trialscribe"
    monkeypatch.setenv("DATABASE_URL", database_url)

    settings = DatabaseSettings()

    assert settings.connection_url() == database_url
    assert "local-password" not in repr(settings)


def test_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError) as error:
        DatabaseSettings()

    assert "DATABASE_URL" not in str(error.value) or "Field required" in str(error.value)


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql+asyncpg://trialscribe:do-not-print@localhost/trialscribe",
        "sqlite:///do-not-print.db",
        "postgresql+psycopg://trialscribe:do-not-print@",
        "not-a-url-do-not-print",
    ],
)
def test_rejects_invalid_or_wrong_driver_urls_without_leaking_input(
    monkeypatch: pytest.MonkeyPatch,
    database_url: str,
) -> None:
    monkeypatch.setenv("DATABASE_URL", database_url)

    with pytest.raises(ValidationError) as error:
        DatabaseSettings()

    assert "do-not-print" not in str(error.value)
