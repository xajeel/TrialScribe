# worker-service

**Status:** planned

Runs long-running work outside the request/response cycle. Today, `POST
/sessions/{id}/generate-report` blocks on the full planner → researcher → writer pipeline for
the duration of the HTTP request. This service will move that execution to a background job
queue with status polling.

## Planned responsibility

- Execute the LangGraph pipeline (and future PubMed/Tavily research calls) as background jobs.
- Job status tracking (queued / running / done / failed) with progress per protocol section.
- Retry and dead-letter handling for failed generation jobs.

## Planned tech stack

Celery or ARQ with Redis as the broker/result backend, sharing the `trialscribe-ai` package
as a dependency for the actual pipeline logic.

## Planned API surface

- `POST /jobs/generate-report` — enqueue a report-generation job, returns a job ID.
- `GET /jobs/{job_id}` — poll job status and progress.
- `GET /jobs/{job_id}/result` — fetch the completed report once done.
- `DELETE /jobs/{job_id}` — cancel a queued or running job.
