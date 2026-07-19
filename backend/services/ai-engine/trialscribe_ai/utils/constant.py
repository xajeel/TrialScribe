"""Stable AI-engine constants and environment-backed tuning values."""

from datetime import timedelta
from pathlib import Path

APP_TITLE = "TrialScribe API"
APP_VERSION = "2.0.0"
APP_DESCRIPTION = "Multi-user clinical trial protocol generation API"
SERVICE_NAME = "ai-engine"
LIVENESS_STATUS = "ok"
READINESS_STATUS = "ready"
SERVICE_UNAVAILABLE_DETAIL = "Service unavailable"

CONVERSATION_TITLE_MAX_LENGTH = 120
CONVERSATION_CONTENT_MAX_LENGTH = 20_000
COLLABORATOR_LIMIT = 100
DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 100

TITLE_VALIDATION_MESSAGE = "Title must be 1 to 120 characters"
MESSAGE_CONTENT_VALIDATION_MESSAGE = "Message must be 1 to 20000 characters"
CONVERSATION_NOT_FOUND_DETAIL = "Conversation not found"
CONVERSATION_PERMISSION_DENIED_DETAIL = "Conversation permission denied"
CONVERSATION_ARCHIVED_DETAIL = "Conversation is archived"
INVALID_CONVERSATION_INPUT_DETAIL = "Invalid conversation input"
COLLABORATOR_CONFLICT_DETAIL = "Collaborators must be organization members"
INVALID_CURSOR_DETAIL = "Invalid pagination cursor"
INVALID_ACCOUNT_CONTEXT_DETAIL = "Invalid account context"
INVALID_ORGANIZATION_CONTEXT_DETAIL = "Invalid organization context"
INTERNAL_ACCOUNT_ID_HEADER = "X-TrialScribe-Account-ID"
INTERNAL_ORGANIZATION_ID_HEADER = "X-TrialScribe-Organization-ID"

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
ALLOWED_WEBSITES_FILE = CONFIG_DIR / "allowed_websites.yml"

DEFAULT_MAX_RESULTS = 5
DEFAULT_K_VALUE = 10
DEFAULT_NUM_WORDS = 500

SESSION_TIMEOUT = timedelta(hours=2)
SESSION_CLEANUP_INTERVAL_SECONDS = 3600

SESSION_NOT_FOUND_DETAIL = "Session not found"
SESSION_EXPIRED_DETAIL = "Session expired"
INVALID_JSON_DETAIL = "Invalid JSON file"
UNSUPPORTED_DOCUMENT_DETAIL = "Only PDF files are supported"
TRIAL_PROCESSING_FAILED_DETAIL = "Trial data processing failed"
DOCUMENT_UPLOAD_FAILED_DETAIL = "Document upload failed"
MISSING_TRIAL_DATA_DETAIL = "No JSON data found. Please upload trial JSON first."
MISSING_DOCUMENTS_DETAIL = (
    "No supporting documents found. Please upload documents first."
)
REPORT_GENERATION_FAILED_DETAIL = "Report generation failed"
