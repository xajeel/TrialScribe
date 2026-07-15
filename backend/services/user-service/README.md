# user-service

**Status:** runnable shell

The user service currently exposes only process health. User records, organizations,
ownership, persistence, and report history are deferred to later features.

From `backend/`, run it directly with:

```bash
uv run --package trialscribe-user uvicorn trialscribe_user.api.app:app --host 0.0.0.0 --port 8002
```

Health is available at `GET /health/live` and `GET /health/ready`.
