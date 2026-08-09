"""Stable worker-service constants."""

APP_TITLE = "TrialScribe Worker"
APP_VERSION = "0.1.0"
SERVICE_NAME = "worker-service"
LIVENESS_STATUS = "ok"
READINESS_STATUS = "ready"

MAX_JOB_KIND_LENGTH = 50
MAX_JOB_STATUS_LENGTH = 20
MAX_JOB_ERROR_CODE_LENGTH = 40
MIN_PROGRESS = 0
MAX_PROGRESS = 100

JOB_STATUS_SQL_VALUES = "'queued', 'running', 'retrying', 'succeeded', 'failed', 'cancelled'"
JOB_ACTIVE_STATUS_SQL_VALUES = "'queued', 'running', 'retrying'"
JOB_TERMINAL_STATUS_SQL_VALUES = "'succeeded', 'failed', 'cancelled'"
JOB_ERROR_CODE_SQL_VALUES = "'handler_failed', 'unsupported_kind', 'cancelled'"

JOB_STATUS_CHECK = f"status IN ({JOB_STATUS_SQL_VALUES})"
JOB_ERROR_CODE_CHECK = f"error_code IS NULL OR error_code IN ({JOB_ERROR_CODE_SQL_VALUES})"
JOB_PROGRESS_CHECK = f"progress BETWEEN {MIN_PROGRESS} AND {MAX_PROGRESS}"
JOB_ATTEMPT_CHECK = "attempt >= 0"
JOB_COMPLETION_CHECK = (
    f"(status IN ({JOB_TERMINAL_STATUS_SQL_VALUES}) AND finished_at IS NOT NULL) "
    f"OR (status IN ({JOB_ACTIVE_STATUS_SQL_VALUES}) AND finished_at IS NULL)"
)
JOB_ORGANIZATION_STATUS_INDEX = "ix_jobs_organization_status_created"

JOB_PROGRESS_KEY_PREFIX = "trialscribe:job:progress:"
JOB_CANCEL_KEY_PREFIX = "trialscribe:job:cancel:"
JOB_CANCEL_FLAG_VALUE = "1"

JOB_NOT_FOUND_DETAIL = "job not found"
JOB_ALREADY_FINISHED_DETAIL = "job already finished"
INVALID_JOB_INPUT_DETAIL = "job request is not valid"
UNSUPPORTED_JOB_KIND_DETAIL = "job kind is not supported"

INTERNAL_ACCOUNT_ID_HEADER = "X-TrialScribe-Account-ID"
INTERNAL_ORGANIZATION_ID_HEADER = "X-TrialScribe-Organization-ID"
INVALID_ACCOUNT_CONTEXT_DETAIL = "Invalid account context"
INVALID_ORGANIZATION_CONTEXT_DETAIL = "Invalid organization context"
SERVICE_UNAVAILABLE_DETAIL = "Service temporarily unavailable"

PROBE_DEFAULT_STEPS = 4
PROBE_MAX_STEPS = 100
PROBE_DEFAULT_STEP_SECONDS = 0.05
PROBE_MAX_STEP_SECONDS = 1.0
PROBE_STEPS_PARAMETER = "steps"
PROBE_STEP_SECONDS_PARAMETER = "step_seconds"
PROBE_FAIL_ATTEMPTS_PARAMETER = "fail_attempts"
