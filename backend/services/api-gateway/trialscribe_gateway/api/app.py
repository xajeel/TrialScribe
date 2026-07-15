from fastapi import FastAPI

from trialscribe_gateway.models.health import HealthResponse

app: FastAPI = FastAPI(title="TrialScribe Gateway", version="0.1.0")


@app.get("/health/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    return HealthResponse(status="ok", service="api-gateway", version=app.version)


@app.get("/health/ready", response_model=HealthResponse)
async def readiness() -> HealthResponse:
    return HealthResponse(status="ready", service="api-gateway", version=app.version)
