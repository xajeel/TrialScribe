"""Opaque keyset pagination cursors, shared by every listing that pages.

A cursor names the exact row a page stopped on — a timestamp plus a tiebreaking
id — so the next page resumes there instead of counting rows with OFFSET, which
gets slower the deeper a caller reads and can skip or repeat rows when the table
changes underneath. The encoding is deliberately opaque: callers hand it back
unchanged and never build one.
"""

import base64
import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_
from sqlalchemy.sql.elements import ColumnElement

from trialscribe_ai.utils.exceptions import InvalidCursorError

_ID_FIELD = "id"
_SEQUENCE_FIELD = "sequence"


def encode_cursor(field: str, moment: datetime, identifier: UUID) -> str:
    """Return the cursor naming the last row of a page."""

    payload = json.dumps(
        {field: moment.isoformat(), _ID_FIELD: str(identifier)},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_cursor(field: str, cursor: str) -> tuple[datetime, UUID]:
    """Read a cursor this service issued, or refuse it.

    Anything malformed, truncated, re-encoded, or naming other fields is refused
    rather than guessed at, so a hand-made cursor cannot steer a query.
    """

    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(
            base64.b64decode(cursor + padding, altchars=b"-_", validate=True)
        )
        if set(payload) != {field, _ID_FIELD}:
            raise ValueError
        moment = datetime.fromisoformat(payload[field])
        if moment.tzinfo is None:
            raise ValueError
        return moment, UUID(payload[_ID_FIELD])
    except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        raise InvalidCursorError from None


def before(
    ordered_column: ColumnElement[datetime],
    id_column: ColumnElement[UUID],
    moment: datetime,
    identifier: UUID,
) -> ColumnElement[bool]:
    """Return the filter selecting rows strictly after a cursor's position.

    Descending order means "after the cursor" is "older than it": a lower
    timestamp, or the same timestamp with a lower id.
    """

    return or_(
        ordered_column < moment,
        and_(ordered_column == moment, id_column < identifier),
    )


def encode_sequence_cursor(sequence: int) -> str:
    """Return the cursor naming an append-only stream position."""

    payload = json.dumps({_SEQUENCE_FIELD: sequence}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_sequence_cursor(cursor: str) -> int:
    """Read a stream-position cursor this service issued, or refuse it."""

    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(
            base64.b64decode(cursor + padding, altchars=b"-_", validate=True)
        )
        if set(payload) != {_SEQUENCE_FIELD}:
            raise ValueError
        sequence = payload[_SEQUENCE_FIELD]
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
            raise ValueError
        return sequence
    except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        raise InvalidCursorError from None
