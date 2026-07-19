# Conversation workspaces

Conversation workspaces are the durable memory boundary of the TrialScribe AI Engine. A
workspace has a title, an owning account, one organization, an archive state, selected
collaborators, and an ordered history of user and assistant messages.

The important distinction is between product memory and workflow state:

- PostgreSQL conversation and message rows are product memory. Users can list and read them,
  and they survive logout, service restart, and PostgreSQL restart.
- A future LangGraph checkpoint may remember where one AI execution paused. It can reference a
  conversation, but it does not replace the conversation's visible message history.
- Redis is for temporary coordination and future job progress. It is not the source of truth
  for conversation history.

The existing process-local `/sessions` endpoints are transitional. Later document ingestion,
M11 section workspaces, and generation jobs attach to the durable conversation UUID instead of
depending on a session dictionary that expires with one AI Engine process.

## Request flow

Clients call the public API gateway, not the AI Engine directly:

```text
Browser
  Authorization: Bearer <access token>
  X-Organization-ID: <selected organization>
             │
             ▼
API gateway verifies token and current membership
             │
             ▼
AI Engine receives trusted account + organization IDs
             │
             ▼
PostgreSQL filters conversation, access, and message rows by organization
```

For example, public `POST /v1/ai/conversations` becomes internal
`POST /conversations`. The gateway removes any browser-supplied internal identity headers and
writes verified `X-TrialScribe-Account-ID` and `X-TrialScribe-Organization-ID` values itself.
Those internal headers are deployment contracts between services, not a public authentication
mechanism.

## Permissions

| Action | Creator | Selected collaborator | Unlisted organization member |
|---|:---:|:---:|:---:|
| List and open | Yes | Yes | No |
| Read ordered messages | Yes | Yes | No |
| Append a user message | Yes | Yes | No |
| Rename | Yes | No | No |
| Archive or restore | Yes | No | No |
| Replace collaborators | Yes | No | No |

Only current members of the conversation's organization can be selected. Removing a person's
organization membership cascades its conversation access grants immediately. Unknown,
cross-organization, and unshared conversations all return the same `404` response so callers
cannot discover private workspace IDs.

## Archive behavior

`DELETE` archives rather than permanently deleting. Archived conversations and messages remain
in PostgreSQL, disappear from the default active list, and reject new messages until the creator
restores them. Archiving and restoring are idempotent: repeating either operation leaves the
workspace in the requested state.

There is no public hard-delete endpoint in this feature. This prevents accidental loss and lets
future documents, sections, evidence, and jobs safely reference a conversation.

## Message ordering and pagination

Messages are append-only. Public callers submit only `content`; the API always stores that
message as `user`, so a browser cannot forge an assistant response. Future AI orchestration uses
an internal service method to append `assistant` messages with no user author ID.

Appending locks the conversation row inside one database transaction, allocates the next
positive sequence number, and updates `last_activity_at`. This gives concurrent writes one
unambiguous order. Message content cannot be updated or individually deleted.

Conversation lists use newest activity first; message lists use sequence order from oldest to
newest. Both return an opaque `next_cursor`:

```json
{
  "items": [],
  "next_cursor": "opaque-value-or-null"
}
```

Pass that cursor back unchanged. Clients must not decode or construct it. Page size defaults to
20 and is limited to 1–100.

## Public endpoints

All paths below are gateway paths and require `Authorization` plus `X-Organization-ID`.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/ai/conversations` | Create a conversation |
| `GET` | `/v1/ai/conversations` | List active or archived accessible conversations |
| `GET` | `/v1/ai/conversations/{id}` | Open one accessible conversation |
| `PATCH` | `/v1/ai/conversations/{id}` | Creator renames it |
| `DELETE` | `/v1/ai/conversations/{id}` | Creator archives it |
| `POST` | `/v1/ai/conversations/{id}/restore` | Creator restores it |
| `PUT` | `/v1/ai/conversations/{id}/collaborators` | Creator replaces access list |
| `POST` | `/v1/ai/conversations/{id}/messages` | Append a user message |
| `GET` | `/v1/ai/conversations/{id}/messages` | Read ordered message history |

Create a conversation:

```http
POST /v1/ai/conversations
Authorization: Bearer <access-token>
X-Organization-ID: 6ee39f73-82a6-45e3-8aa1-a4193a48a3b3
Content-Type: application/json

{"title":"Phase 2 protocol"}
```

Share with an exact set of collaborators:

```http
PUT /v1/ai/conversations/{conversation-id}/collaborators
Authorization: Bearer <access-token>
X-Organization-ID: 6ee39f73-82a6-45e3-8aa1-a4193a48a3b3
Content-Type: application/json

{"account_ids":["a9f6cfe8-397f-40f1-a23a-9f04b53d191f"]}
```

The collaborator list is replacement-based: accounts omitted from a later request lose access.
The creator does not need to include their own account ID and is never returned as a
collaborator.

## Safe errors

| Status | Meaning |
|---:|---|
| `401` | Trusted account context is missing |
| `403` | A collaborator attempted a creator-only action |
| `404` | Conversation is missing, belongs to another organization, or is not shared |
| `409` | Conversation is archived or collaborator membership conflicts |
| `422` | Header, body, page limit, or cursor is malformed |
| `503` | PostgreSQL readiness check failed |

Validation responses remove raw input. Database queries, connection strings, exception text,
message content, and stack traces are never used as public error details.

## Local verification

Run the isolated lifecycle test from the repository root:

```bash
./scripts.sh ai test
```

It starts a clean PostgreSQL project on a Docker-assigned loopback port, migrates to the current
head, creates and shares multiple conversations, verifies cross-tenant isolation and pagination,
restarts PostgreSQL, verifies exact message history, removes a collaborator's membership, and
then removes the test containers and volume.
