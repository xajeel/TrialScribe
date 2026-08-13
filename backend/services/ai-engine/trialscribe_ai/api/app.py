from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from trialscribe_db.config import DatabaseSettings
from trialscribe_db.runtime import create_database_runtime

from trialscribe_ai.api.conversations import router as conversation_router
from trialscribe_ai.api.documents import router as document_router
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
app.include_router(m11_section_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AIEngineError)
async def ai_engine_error_response(
    _request: Request,
    error: AIEngineError,
) -> JSONResponse:
    """Translate expected failures without exposing exception text."""

    if isinstance(error, ConversationNotFoundError):
        status_code, detail = 404, CONVERSATION_NOT_FOUND_DETAIL
    elif isinstance(error, ConversationPermissionDeniedError):
        status_code, detail = 403, CONVERSATION_PERMISSION_DENIED_DETAIL
    elif isinstance(error, ConversationArchivedError):
        status_code, detail = 409, CONVERSATION_ARCHIVED_DETAIL
    elif isinstance(error, CollaboratorConflictError):
        status_code, detail = 409, COLLABORATOR_CONFLICT_DETAIL
    elif isinstance(error, InvalidCursorError):
        status_code, detail = 422, INVALID_CURSOR_DETAIL
    elif isinstance(error, InvalidConversationInputError):
        status_code, detail = 422, INVALID_CONVERSATION_INPUT_DETAIL
    elif isinstance(error, DocumentNotFoundError):
        status_code, detail = 404, DOCUMENT_NOT_FOUND_DETAIL
    elif isinstance(error, UnsupportedDocumentTypeError):
        status_code, detail = 415, UNSUPPORTED_DOCUMENT_TYPE_DETAIL
    elif isinstance(error, DocumentTooLargeError):
        status_code, detail = 413, DOCUMENT_TOO_LARGE_DETAIL
    elif isinstance(error, InvalidTrialDataError):
        status_code, detail = 422, INVALID_TRIAL_DATA_DETAIL
    elif isinstance(error, EmptyDocumentError):
        status_code, detail = 422, EMPTY_DOCUMENT_DETAIL
    elif isinstance(error, M11SectionNotFoundError):
        status_code, detail = 404, M11_SECTION_NOT_FOUND_DETAIL
    elif isinstance(error, InvalidM11SectionInputError):
        status_code, detail = 422, INVALID_M11_SECTION_INPUT_DETAIL
    elif isinstance(error, M11SectionRevisionConflictError):
        status_code, detail = 409, M11_SECTION_REVISION_CONFLICT_DETAIL
    elif isinstance(error, M11SectionTransitionError):
        status_code, detail = 409, M11_SECTION_TRANSITION_DETAIL
    else:
        status_code, detail = 500, SERVICE_UNAVAILABLE_DETAIL
    return JSONResponse(status_code=status_code, content={"detail": detail})


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
