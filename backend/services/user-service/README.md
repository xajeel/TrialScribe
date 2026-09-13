# user-service

**Status:** organization and RBAC boundary

The user service owns organizations, memberships, invitation links, and the
`owner`/`admin`/`member` permission matrix. Authentication remains a separate boundary: this
service receives only its Ed25519 public key and verifies the global account ID in access
tokens before loading current organization access from PostgreSQL.

From `backend/`, run it directly with:

```bash
uv run --env-file ../.env --package trialscribe-user uvicorn trialscribe_user.api.app:app --host 0.0.0.0 --port 8002
```

Health is available at `GET /health/live` and `GET /health/ready`; API documentation is at
`http://localhost:8002/docs`. From the repository root, prefer `./scripts.sh run user`.

Login is organization-neutral. A valid account can call `POST /v1/organizations`, list its
memberships with `GET /v1/organizations`, or accept a link through
`POST /v1/organization-invitations/accept`. Organization-scoped member and invitation routes
live below `/v1/organizations/{organization_id}`.

Invitation creation returns `accept_url` once. Only its SHA-256 hash is stored; list responses
never return the URL, token, or hash. Until an email-delivery boundary exists, the owner or
admin must securely deliver that URL to the intended person. Links expire after seven days,
are single-use, and should only be sent over HTTPS outside local development.

Run `./scripts.sh user test` from the repository root for the isolated PostgreSQL lifecycle.
It creates, restarts, and then removes the `trialscribe-user-test` Compose project and volume.
