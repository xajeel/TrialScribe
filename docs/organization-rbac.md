# TrialScribe Organizations and RBAC

The user service decides what an authenticated person may do inside an organization. Login
still belongs to the authentication service: there is no individual-versus-organization
checkbox or organization dropdown. A person logs in once, then creates an organization or
accepts an invitation after login.

## Flow

```text
Global account logs in
        │
        ├── creates organization ──> owner membership
        │
        └── accepts one-time link ─> admin or member membership
                                      │
Organization request ─> verify JWT ─> load current membership ─> allow or deny
```

An account can have no organization, belong to several organizations, or own several. The
organization UUID in each route selects the workspace; roles are never chosen at login and
never trusted from browser-supplied account or organization fields.

## Roles

| Action | Owner | Admin | Member |
|---|---:|---:|---:|
| Read organization and members | Yes | Yes | Yes |
| Invite a member | Yes | Yes | No |
| Invite an admin | Yes | No | No |
| Revoke/remove member access | Yes | Yes | No |
| Change roles or manage admins/owners | Yes | No | No |

Several owners are allowed, but the service locks membership rows and rejects any change that
would remove or demote the last owner. Permissions come from PostgreSQL on every protected
request, so a role change or removal applies immediately without waiting for the 15-minute
access token to expire.

## API routes

| Method | Route | Purpose |
|---|---|---|
| `POST` | `/v1/organizations` | Create an organization and become owner |
| `GET` | `/v1/organizations` | List the current account's organizations |
| `GET` | `/v1/organizations/{organization_id}` | Read one visible organization |
| `GET` | `/v1/organizations/{organization_id}/members` | List current memberships |
| `PATCH` | `/v1/organizations/{organization_id}/members/{account_id}` | Change a role |
| `DELETE` | `/v1/organizations/{organization_id}/members/{account_id}` | Remove access |
| `POST` | `/v1/organizations/{organization_id}/invitations` | Create a one-time link |
| `GET` | `/v1/organizations/{organization_id}/invitations` | List invitation metadata |
| `DELETE` | `/v1/organizations/{organization_id}/invitations/{invitation_id}` | Revoke a link |
| `POST` | `/v1/organization-invitations/accept` | Accept a link as the logged-in account |

All routes require `Authorization: Bearer <access-token>`. A missing or invalid token returns
the same generic `401`. An organization that the account cannot see returns `404`, while an
insufficient role in a visible organization returns `403`.

## Invitation safety and delivery

The service creates 32 random bytes and places the URL-safe value in `accept_url`. PostgreSQL
stores only its SHA-256 hash, expiry, accepted time, and revoked time. The raw link is returned
only by the creation response; invitation lists never contain it. A valid link works once for
seven days, and unknown, expired, revoked, consumed, and modified values share one safe error.

Email delivery is not implemented yet. For now, the owner or admin who creates the invitation
must copy the returned link and securely deliver it to the intended person. Production links
must use the configured HTTPS frontend URL and must not be logged. A future email worker can
deliver the same one-time URL without changing membership or acceptance rules.

## Local use

```bash
./scripts.sh env
./scripts.sh infra up
./scripts.sh db migrate
./scripts.sh auth keys
./scripts.sh run auth  # terminal 1
./scripts.sh run user  # terminal 2
```

Open `http://localhost:8001/docs` to register/login and
`http://localhost:8002/docs` for organization routes. Copy the access token returned by login
into the user service OpenAPI authorization dialog.

Run `./scripts.sh user test` for the destructive isolated test. It uses only the
`trialscribe-user-test` Compose project, verifies migration, JWT validation, organization
creation, multi-organization isolation, invitations, all roles, immediate revocation,
last-owner protection, PostgreSQL restart persistence, and then removes its test containers,
network, and volume.
