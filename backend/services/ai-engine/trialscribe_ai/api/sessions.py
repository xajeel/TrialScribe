from pydantic import BaseModel
from uuid import uuid4
import asyncio
from datetime import datetime
from typing import Any

from trialscribe_ai.storage.evidence_db import EvidenceDatabase
from trialscribe_ai.agents.graph import graph_builder
from trialscribe_ai.utils.constant import (
    SESSION_CLEANUP_INTERVAL_SECONDS,
    SESSION_TIMEOUT,
)
from trialscribe_ai.utils.exceptions import SessionExpiredError, SessionNotFoundError


class SessionResponse(BaseModel):
    session_id: str
    message: str


class QueryRequest(BaseModel):
    query: str


# Session management
class SessionManager:
    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, Any]] = {}

    def create_session(self) -> str:
        session_id = str(uuid4())
        self.sessions[session_id] = {
            "created_at": datetime.now(),
            "database": EvidenceDatabase(),
            "agent": graph_builder(),
            "summary": None,
            "documents": [],
            "reports": {},
        }
        return session_id

    def get_session(self, session_id: str) -> dict[str, Any]:
        if session_id not in self.sessions:
            raise SessionNotFoundError

        session = self.sessions[session_id]

        if datetime.now() - session["created_at"] > SESSION_TIMEOUT:
            del self.sessions[session_id]
            raise SessionExpiredError

        return session

    def delete_session(self, session_id: str) -> None:
        if session_id not in self.sessions:
            raise SessionNotFoundError
        del self.sessions[session_id]

    def cleanup_expired_sessions(self) -> None:
        expired_sessions = []
        for session_id, session in self.sessions.items():
            if datetime.now() - session["created_at"] > SESSION_TIMEOUT:
                expired_sessions.append(session_id)

        for session_id in expired_sessions:
            del self.sessions[session_id]


session_manager = SessionManager()


# get session
def get_session(session_id: str) -> dict[str, Any]:
    return session_manager.get_session(session_id)


# Background task for session cleanup
async def cleanup_sessions() -> None:
    while True:
        session_manager.cleanup_expired_sessions()
        await asyncio.sleep(SESSION_CLEANUP_INTERVAL_SECONDS)
