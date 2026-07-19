from fastapi import FastAPI

from trialscribe_worker.models.health import HealthResponse
from trialscribe_worker.utils.constant import (
    APP_TITLE,
    APP_VERSION,
    LIVENESS_STATUS,
    READINESS_STATUS,
    SERVICE_NAME,
)

app: FastAPI = FastAPI(title=APP_TITLE, version=APP_VERSION)


@app.get("/health/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    return HealthResponse(
        status=LIVENESS_STATUS,
        service=SERVICE_NAME,
        version=app.version,
    )


@app.get("/health/ready", response_model=HealthResponse)
async def readiness() -> HealthResponse:
    return HealthResponse(
        status=READINESS_STATUS,
        service=SERVICE_NAME,
        version=app.version,
    )
