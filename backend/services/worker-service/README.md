# worker-service

**Status:** runnable shell

The worker currently exposes only a health companion application. Queues, polling, job
execution, retries, progress tracking, and AI pipeline integration are deferred to later
features.

From `backend/`, run it directly with:

```bash
uv run --package trialscribe-worker uvicorn trialscribe_worker.api.app:app --host 0.0.0.0 --port 8004
```

Health is available at `GET /health/live` and `GET /health/ready`.
