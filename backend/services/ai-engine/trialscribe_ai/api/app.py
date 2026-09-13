from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text

from trialscribe_db.config import DatabaseSettings
from trialscribe_db.runtime import create_database_runtime
from trialscribe_observability.http import instrument_app

from trialscribe_ai.api.conversations import router as conversation_router
from trialscribe_ai.api.documents import router as document_router
from trialscribe_ai.api.evidence import router as evidence_router
from trialscribe_ai.api.m11_sections import router as m11_section_router
from trialscribe_ai.models.health import HealthResponse
from trialscribe_ai.utils.constant import (
    APP_DESCRIPTION,
    APP_TITLE,
    APP_VERSION,
    COLLABORATOR_CONFLICT_DETAIL,
    CONVERSATION_ARCHIVED_DETAIL,
    CONVERSATION_NOT_FOUND_DETAIL,
    CONVERSATION_PERMISSION_DENIED_DETAIL,
    DOCUMENT_NOT_FOUND_DETAIL,
    DOCUMENT_TOO_LARGE_DETAIL,
    EMPTY_DOCUMENT_DETAIL,
    INVALID_EVIDENCE_IDS_DETAIL,
    INVALID_M11_SECTION_INPUT_DETAIL,
    INVALID_TRIAL_DATA_DETAIL,
    INVALID_CONVERSATION_INPUT_DETAIL,
    INVALID_CURSOR_DETAIL,
    M11_SECTION_NOT_FOUND_DETAIL,
    M11_SECTION_REVISION_CONFLICT_DETAIL,
    M11_SECTION_TRANSITION_DETAIL,
    LIVENESS_STATUS,
    READINESS_STATUS,
    SERVICE_NAME,
    SERVICE_UNAVAILABLE_DETAIL,
    UNSUPPORTED_DOCUMENT_TYPE_DETAIL,
)
from trialscribe_ai.utils.exceptions import (
    AIEngineError,
    CollaboratorConflictError,
    ConversationArchivedError,
    ConversationNotFoundError,
    ConversationPermissionDeniedError,
    DocumentNotFoundError,
    DocumentTooLargeError,
    EmptyDocumentError,
    InvalidEvidenceRequestError,
    InvalidM11SectionInputError,
    InvalidConversationInputError,
    InvalidCursorError,
    InvalidTrialDataError,
    M11SectionNotFoundError,
    M11SectionRevisionConflictError,
    M11SectionTransitionError,
    UnsupportedDocumentTypeError,
)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Own the durable database runtime for conversation workspaces."""

    application.state.database_runtime = create_database_runtime(DatabaseSettings())
    try:
        yield
    finally:
        await application.state.database_runtime.dispose()


app: FastAPI = FastAPI(
    title=APP_TITLE,
    version=APP_VERSION,
    description=APP_DESCRIPTION,
    lifespan=lifespan,
)
app.include_router(conversation_router)
app.include_router(document_router)
app.include_router(evidence_router)
app.include_router(m11_section_router)


_ERROR_RESPONSES: tuple[tuple[type[AIEngineError], int, str], ...] = (
    (ConversationNotFoundError, 404, CONVERSATION_NOT_FOUND_DETAIL),
    (ConversationPermissionDeniedError, 403, CONVERSATION_PERMISSION_DENIED_DETAIL),
    (ConversationArchivedError, 409, CONVERSATION_ARCHIVED_DETAIL),
    (CollaboratorConflictError, 409, COLLABORATOR_CONFLICT_DETAIL),
    (InvalidCursorError, 422, INVALID_CURSOR_DETAIL),
    (InvalidConversationInputError, 422, INVALID_CONVERSATION_INPUT_DETAIL),
    (DocumentNotFoundError, 404, DOCUMENT_NOT_FOUND_DETAIL),
    (UnsupportedDocumentTypeError, 415, UNSUPPORTED_DOCUMENT_TYPE_DETAIL),
    (DocumentTooLargeError, 413, DOCUMENT_TOO_LARGE_DETAIL),
    (InvalidTrialDataError, 422, INVALID_TRIAL_DATA_DETAIL),
    (EmptyDocumentError, 422, EMPTY_DOCUMENT_DETAIL),
    (InvalidEvidenceRequestError, 422, INVALID_EVIDENCE_IDS_DETAIL),
    (M11SectionNotFoundError, 404, M11_SECTION_NOT_FOUND_DETAIL),
    (InvalidM11SectionInputError, 422, INVALID_M11_SECTION_INPUT_DETAIL),
    (M11SectionRevisionConflictError, 409, M11_SECTION_REVISION_CONFLICT_DETAIL),
    (M11SectionTransitionError, 409, M11_SECTION_TRANSITION_DETAIL),
)
"""Which public answer each expected failure earns.

Ordered most specific first, so a subclass never matches its parent's row. The
detail strings are fixed and allow-listed: an exception's own text never reaches
a caller.
"""


@app.exception_handler(AIEngineError)
async def ai_engine_error_response(
    _request: Request,
    error: AIEngineError,
) -> JSONResponse:
    """Translate expected failures without exposing exception text."""

    for error_type, status_code, detail in _ERROR_RESPONSES:
        if isinstance(error, error_type):
            return JSONResponse(status_code=status_code, content={"detail": detail})
    return JSONResponse(status_code=500, content={"detail": SERVICE_UNAVAILABLE_DETAIL})


@app.exception_handler(RequestValidationError)
async def request_validation_error(
    _request: Request,
    error: RequestValidationError,
) -> JSONResponse:
    safe_errors = [
        {key: value for key, value in item.items() if key != "input"}
        for item in error.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(safe_errors)},
    )


@app.get("/health/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    return HealthResponse(
        status=LIVENESS_STATUS,
        service=SERVICE_NAME,
        version=app.version,
    )


@app.get("/health/ready", response_model=HealthResponse)
async def readiness(request: Request) -> HealthResponse:
    try:
        async with request.app.state.database_runtime.transaction() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(
            status_code=503,
            detail=SERVICE_UNAVAILABLE_DETAIL,
        ) from None
    return HealthResponse(
        status=READINESS_STATUS,
        service=SERVICE_NAME,
        version=request.app.version,
    )


instrument_app(app, service=SERVICE_NAME)
