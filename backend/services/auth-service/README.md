# auth-service

**Status:** runnable shell

The authentication service currently exposes only process health. Identity, tokens,
authorization, persistence, and session revocation are deferred to later features.

From `backend/`, run it directly with:

```bash
uv run --package trialscribe-auth uvicorn trialscribe_auth.api.app:app --host 0.0.0.0 --port 8001
```

Health is available at `GET /health/live` and `GET /health/ready`.
