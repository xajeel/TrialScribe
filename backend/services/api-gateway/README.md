# api-gateway

**Status:** runnable shell

The gateway currently exposes only process health. Proxying, routing, authentication
enforcement, and downstream service integration are deferred to later features.

From `backend/`, run it directly with:

```bash
uv run --package trialscribe-gateway uvicorn trialscribe_gateway.api.app:app --host 0.0.0.0 --port 8000
```

Health is available at `GET /health/live` and `GET /health/ready`.
