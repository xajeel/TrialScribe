# app.py
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import json
from uuid import uuid4
import tempfile
import shutil
import os
import asyncio
from datetime import datetime, timedelta
import uvicorn
from contextlib import asynccontextmanager

from utils.retrievers.trialprocessor import TrialDataProcessor
from src.database import EvidenceDatabase
from main import graph_builder
from config.schemas import AgentState

app = FastAPI(
    title="TrialScribe API",
    version="2.0.0",
    description="Multi-user clinical trial protocol generation API"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

trial_processor = TrialDataProcessor()

# In-memory session storage 
ACTIVE_SESSIONS = {}
SESSION_TIMEOUT = timedelta(hours=2)


class SessionResponse(BaseModel):
    session_id: str
    message: str

class QueryRequest(BaseModel):
    query: str


# Session management
class SessionManager:
    def __init__(self):
        self.sessions = ACTIVE_SESSIONS
    
    def create_session(self) -> str:
        session_id = str(uuid4())
        self.sessions[session_id] = {
            "created_at": datetime.now(),
            "database": EvidenceDatabase(),
            "agent": graph_builder(),
            "summary": None,
            "documents": [],
            "reports": {}
        }
        return session_id
    
    def get_session(self, session_id: str):
        if session_id not in self.sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        
        session = self.sessions[session_id]

        if datetime.now() - session["created_at"] > SESSION_TIMEOUT:
            del self.sessions[session_id]
            raise HTTPException(status_code=404, detail="Session expired")
        
        return session
    
    def cleanup_expired_sessions(self):
        expired_sessions = []
        for session_id, session in self.sessions.items():
            if datetime.now() - session["created_at"] > SESSION_TIMEOUT:
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            del self.sessions[session_id]

session_manager = SessionManager()

# get session
def get_session(session_id: str):
    return session_manager.get_session(session_id)

# Background task for session cleanup
async def cleanup_sessions():
    while True:
        session_manager.cleanup_expired_sessions()
        await asyncio.sleep(3600)  # Run every hour

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Background cleanup task using lifespan event handler"""
    cleanup_task = asyncio.create_task(cleanup_sessions())
    yield
    cleanup_task.cancel()

app = FastAPI(
    lifespan=lifespan
)


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
    uvicorn.run("app2:app", host="localhost", port=8000, reload=True)