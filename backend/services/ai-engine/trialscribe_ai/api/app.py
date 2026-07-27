from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any

import asyncio
from datetime import datetime
import json
import os
import shutil
import tempfile

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from trialscribe_db.config import DatabaseSettings
from trialscribe_db.runtime import create_database_runtime

from trialscribe_ai.api.conversations import router as conversation_router
from trialscribe_ai.api.documents import router as document_router
from trialscribe_ai.api.sessions import (
    QueryRequest,
    SessionResponse,
    cleanup_sessions,
    get_session,
    session_manager,
)
from trialscribe_ai.models.health import HealthResponse
from trialscribe_ai.models.schemas import AgentState
from trialscribe_ai.retrieval.trial_processor import TrialDataProcessor
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
    DOCUMENT_UPLOAD_FAILED_DETAIL,
    EMPTY_DOCUMENT_DETAIL,
    INVALID_JSON_DETAIL,
    INVALID_TRIAL_DATA_DETAIL,
    INVALID_CONVERSATION_INPUT_DETAIL,
    INVALID_CURSOR_DETAIL,
    MISSING_DOCUMENTS_DETAIL,
    MISSING_TRIAL_DATA_DETAIL,
    LIVENESS_STATUS,
    READINESS_STATUS,
    REPORT_GENERATION_FAILED_DETAIL,
    SESSION_EXPIRED_DETAIL,
    SESSION_NOT_FOUND_DETAIL,
    SERVICE_NAME,
    SERVICE_UNAVAILABLE_DETAIL,
    TRIAL_PROCESSING_FAILED_DETAIL,
    UNSUPPORTED_DOCUMENT_DETAIL,
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
    DocumentUploadError,
    EmptyDocumentError,
    InvalidJsonFileError,
    InvalidConversationInputError,
    InvalidCursorError,
    InvalidTrialDataError,
    MissingDocumentsError,
    MissingTrialDataError,
    ReportGenerationError,
    SessionExpiredError,
    SessionNotFoundError,
    TrialProcessingError,
    UnsupportedDocumentError,
    UnsupportedDocumentTypeError,
)

trial_processor = TrialDataProcessor()


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Own durable database and legacy-session cleanup resources."""

    application.state.database_runtime = create_database_runtime(DatabaseSettings())
    cleanup_task = asyncio.create_task(cleanup_sessions())
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task
        await application.state.database_runtime.dispose()


app: FastAPI = FastAPI(
    title=APP_TITLE,
    version=APP_VERSION,
    description=APP_DESCRIPTION,
    lifespan=lifespan,
)
app.include_router(conversation_router)
app.include_router(document_router)

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
    elif isinstance(error, SessionNotFoundError):
        status_code, detail = 404, SESSION_NOT_FOUND_DETAIL
    elif isinstance(error, SessionExpiredError):
        status_code, detail = 404, SESSION_EXPIRED_DETAIL
    elif isinstance(error, InvalidJsonFileError):
        status_code, detail = 400, INVALID_JSON_DETAIL
    elif isinstance(error, UnsupportedDocumentError):
        status_code, detail = 400, UNSUPPORTED_DOCUMENT_DETAIL
    elif isinstance(error, MissingTrialDataError):
        status_code, detail = 400, MISSING_TRIAL_DATA_DETAIL
    elif isinstance(error, MissingDocumentsError):
        status_code, detail = 400, MISSING_DOCUMENTS_DETAIL
    elif isinstance(error, TrialProcessingError):
        status_code, detail = 500, TRIAL_PROCESSING_FAILED_DETAIL
    elif isinstance(error, DocumentUploadError):
        status_code, detail = 500, DOCUMENT_UPLOAD_FAILED_DETAIL
    else:
        status_code, detail = 500, REPORT_GENERATION_FAILED_DETAIL
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


@app.post("/sessions", response_model=SessionResponse)
async def create_session() -> SessionResponse:
    """Create a new user session"""
    session_id = session_manager.create_session()
    return SessionResponse(
        session_id=session_id, message="Session created successfully"
    )


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict[str, str]:
    """Delete a user session"""
    session_manager.delete_session(session_id)
    return {"message": "Session deleted successfully"}


@app.post("/sessions/{session_id}/upload-json")
async def upload_trial_json(
    session_id: str,
    file: UploadFile = File(...),
    session: dict[str, Any] = Depends(get_session),
) -> dict[str, str]:
    """Upload and process trial JSON file for a specific session"""
    try:
        contents = await file.read()
        try:
            trial_data = json.loads(contents)
        except json.JSONDecodeError:
            raise InvalidJsonFileError from None

        json_fields = trial_processor.process_json(trial_data)
        summary = session["database"].add_json_data(json_fields)

        session["summary"] = summary

        return {"session_id": session_id, "message": "JSON file processed successfully"}

    except AIEngineError:
        raise
    except Exception as error:
        raise TrialProcessingError from error


@app.post("/sessions/{session_id}/upload-documents")
async def upload_supporting_docs(
    session_id: str,
    files: list[UploadFile] = File(...),
    session: dict[str, Any] = Depends(get_session),
) -> dict[str, str | int]:
    """Upload supporting documents for a specific session"""
    temp_paths: list[str] = []
    try:
        for file in files:
            if not (file.filename or "").lower().endswith(".pdf"):
                raise UnsupportedDocumentError

            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                shutil.copyfileobj(file.file, tmp)
                temp_paths.append(tmp.name)

        session["database"].add_user_documents(temp_paths)
        session["documents"].extend(temp_paths)

        return {
            "session_id": session_id,
            "message": f"{len(files)} documents uploaded successfully",
            "total_documents": len(session["documents"]),
        }

    except Exception as error:
        for path in temp_paths:
            if os.path.exists(path):
                os.unlink(path)
        if isinstance(error, AIEngineError):
            raise
        raise DocumentUploadError from error


@app.post("/sessions/{session_id}/generate-report")
async def generate_report(
    session_id: str,
    query: QueryRequest,
    session: dict[str, Any] = Depends(get_session),
) -> dict[str, Any]:

    if not session["summary"]:
        raise MissingTrialDataError

    if not session["documents"]:
        raise MissingDocumentsError

    try:
        start_time = datetime.now()

        state = AgentState(
            query=query.query, sections=[], written_texts=[], summary=session["summary"]
        )

        result = await session["agent"].ainvoke(state)

        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()

        return {
            "session_id": session_id,
            "query": query.query,
            "written_texts": result.get("written_texts", []),
            "generated_at": end_time.isoformat(),
            "processing_time_seconds": processing_time,
        }

    except Exception as error:
        raise ReportGenerationError from error
