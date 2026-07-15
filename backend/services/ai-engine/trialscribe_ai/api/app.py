from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import List
import json
import tempfile
import shutil
import os
import asyncio
from datetime import datetime
import uvicorn
from contextlib import asynccontextmanager

from trialscribe_ai.retrieval.trial_processor import TrialDataProcessor
from trialscribe_ai.models.health import HealthResponse
from trialscribe_ai.models.schemas import AgentState
from trialscribe_ai.api.sessions import (
    session_manager,
    get_session,
    cleanup_sessions,
    SessionResponse,
    QueryRequest,
    ACTIVE_SESSIONS,
)

trial_processor = TrialDataProcessor()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Background cleanup task using lifespan event handler"""
    cleanup_task = asyncio.create_task(cleanup_sessions())
    yield
    cleanup_task.cancel()

app: FastAPI = FastAPI(
    title="TrialScribe API",
    version="2.0.0",
    description="Multi-user clinical trial protocol generation API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    return HealthResponse(status="ok", service="ai-engine", version=app.version)


@app.get("/health/ready", response_model=HealthResponse)
async def readiness() -> HealthResponse:
    return HealthResponse(status="ready", service="ai-engine", version=app.version)


@app.post("/sessions", response_model=SessionResponse)
async def create_session():
    """Create a new user session"""
    session_id = session_manager.create_session()
    return SessionResponse(
        session_id=session_id,
        message="Session created successfully"
    )


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a user session"""
    if session_id in ACTIVE_SESSIONS:
        del ACTIVE_SESSIONS[session_id]
        return {"message": "Session deleted successfully"}
    raise HTTPException(status_code=404, detail="Session not found")


@app.post("/sessions/{session_id}/upload-json")
async def upload_trial_json(
    session_id: str,
    file: UploadFile = File(...),
    session = Depends(get_session)
):
    """Upload and process trial JSON file for a specific session"""
    try:
        contents = await file.read()
        try:
            trial_data = json.loads(contents)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON file")

        json_fields = trial_processor.process_json(trial_data)
        summary = session["database"].add_json_data(json_fields)

        session["summary"] = summary

        return {
            "session_id": session_id,
            "message": "JSON file processed successfully"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@app.post("/sessions/{session_id}/upload-documents")
async def upload_supporting_docs(
    session_id: str,
    files: List[UploadFile] = File(...),
    session = Depends(get_session)
):
    """Upload supporting documents for a specific session"""
    try:
        temp_paths = []
        for file in files:
            if not file.filename.lower().endswith('.pdf'):
                raise HTTPException(status_code=400, detail="Only PDF files are supported")

            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                shutil.copyfileobj(file.file, tmp)
                temp_paths.append(tmp.name)

        session["database"].add_user_documents(temp_paths)
        session["documents"].extend(temp_paths)

        return {
            "session_id": session_id,
            "message": f"{len(files)} documents uploaded successfully",
            "total_documents": len(session["documents"])
        }

    except Exception as e:
        for path in temp_paths:
            if os.path.exists(path):
                os.unlink(path)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.post("/sessions/{session_id}/generate-report")
async def generate_report(
    session_id: str,
    query: QueryRequest,
    session = Depends(get_session)
):

    if not session["summary"]:
        raise HTTPException(status_code=400, detail="No JSON data found. Please upload trial JSON first.")

    if not session["documents"]:
        raise HTTPException(status_code=400, detail="No supporting documents found. Please upload documents first.")

    try:
        start_time = datetime.now()

        state = AgentState(
            query=query.query,
            sections=[],
            written_texts=[],
            summary=session["summary"]
        )

        result = await session["agent"].ainvoke(state)

        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()

        return {
            "session_id": session_id,
            "query": query.query,
            "written_texts": result.get("written_texts", []),
            "generated_at": end_time.isoformat(),
            "processing_time_seconds": processing_time
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")


if __name__ == "__main__":
    uvicorn.run("trialscribe_ai.api.app:app", host="localhost", port=8000, reload=True)
