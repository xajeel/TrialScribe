from fastapi import HTTPException
from pydantic import BaseModel
from uuid import uuid4
import asyncio
from datetime import datetime, timedelta

from trialscribe_ai.storage.evidence_db import EvidenceDatabase
from trialscribe_ai.agents.graph import graph_builder

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
