import asyncio
from typing import Any
from uuid import UUID

import pytest

from trialscribe_user.models.identity import OrganizationIdentityLink
from trialscribe_user.repositories.identities import IdentityRepository

ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000081")
ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000082")
SECOND_ACCOUNT_ID = UUID("00000000-0000-4000-8000-000000000083")


class FakeMappingResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> list[dict[str, Any]]:
        return self._rows


class FakeSession:
    def __init__(self) -> None:
        self.existing: UUID | None = None
        self.added: list[OrganizationIdentityLink] = []
        self.flushes = 0
        self.rows: list[dict[str, Any]] = []
        self.parameters: list[dict[str, Any]] = []

    async def scalar(self, _statement: object) -> UUID | None:
        return self.existing

    def add(self, link: OrganizationIdentityLink) -> None:
        self.added.append(link)

    async def flush(self) -> None:
        self.flushes += 1

    async def execute(
        self,
        _statement: object,
        parameters: dict[str, Any],
    ) -> FakeMappingResult:
        self.parameters.append(parameters)
        return FakeMappingResult(self.rows)


def test_association_is_idempotent() -> None:
    session = FakeSession()
    repository = IdentityRepository(session)  # type: ignore[arg-type]

    asyncio.run(repository.associate(ORGANIZATION_ID, ACCOUNT_ID))

    assert len(session.added) == 1
    assert session.added[0].organization_id == ORGANIZATION_ID
    assert session.added[0].account_id == ACCOUNT_ID
    assert session.flushes == 1

    session.existing = ACCOUNT_ID
    asyncio.run(repository.associate(ORGANIZATION_ID, ACCOUNT_ID))
    assert len(session.added) == 1
    assert session.flushes == 1


def test_bulk_resolution_deduplicates_and_returns_allow_listed_fields() -> None:
    session = FakeSession()
    session.rows = [
        {
            "account_id": ACCOUNT_ID,
            "email": "member@example.com",
            "is_active": True,
        }
    ]
    repository = IdentityRepository(session)  # type: ignore[arg-type]

    identities = asyncio.run(
        repository.resolve(
            ORGANIZATION_ID,
            [ACCOUNT_ID, ACCOUNT_ID, SECOND_ACCOUNT_ID],
        )
    )

    assert identities[ACCOUNT_ID].email == "member@example.com"
    assert identities[ACCOUNT_ID].is_active is True
    assert session.parameters == [
        {
            "organization_id": ORGANIZATION_ID,
            "account_ids": (ACCOUNT_ID, SECOND_ACCOUNT_ID),
        }
    ]


def test_bulk_resolution_is_bounded_and_empty_lookup_skips_database() -> None:
    session = FakeSession()
    repository = IdentityRepository(session)  # type: ignore[arg-type]

    assert asyncio.run(repository.resolve(ORGANIZATION_ID, [])) == {}
    assert session.parameters == []
    with pytest.raises(ValueError, match="bounded size"):
        asyncio.run(
            repository.resolve(
                ORGANIZATION_ID,
                [UUID(int=value) for value in range(101)],
            )
        )


def test_internal_resolution_batches_above_public_limit() -> None:
    session = FakeSession()
    repository = IdentityRepository(session)  # type: ignore[arg-type]
    account_ids = [UUID(int=value) for value in range(101)]

    assert asyncio.run(repository.resolve_many(ORGANIZATION_ID, [])) == {}
    assert asyncio.run(
        repository.resolve_many(ORGANIZATION_ID, account_ids[:100])
    ) == {}
    assert [len(parameters["account_ids"]) for parameters in session.parameters] == [
        100
    ]

    session.parameters.clear()
    assert asyncio.run(
        repository.resolve_many(
            ORGANIZATION_ID,
            [*account_ids, account_ids[0]],
        )
    ) == {}

    assert [len(parameters["account_ids"]) for parameters in session.parameters] == [
        100,
        1,
    ]
    assert session.parameters[0]["account_ids"] == tuple(account_ids[:100])
    assert session.parameters[1]["account_ids"] == (account_ids[100],)
