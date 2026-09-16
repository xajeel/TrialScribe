# TrialScribe Authentication Service

The authentication service proves who a person is. It owns individual accounts, password
verification, short-lived access tokens, browser refresh sessions, logout, and protection
against repeated password guessing. It runs as an independent FastAPI application and does
not own organizations, memberships, or roles.

For a simple mental model, imagine entering a building:

- The password proves your identity at reception.
- The access JWT is a signed visitor badge that works for 15 minutes.
- The refresh token is a protected renewal card that can request a new badge.
- The CSRF token proves the renewal request came from the real TrialScribe browser page.
- PostgreSQL is the permanent security ledger.
- Redis is the short-term failed-login counter.

## Service boundary

```text
Browser or API client
        │
        │ HTTP on port 8001 during local development
        ▼
Authentication service
        ├── PostgreSQL: accounts, sessions, and refresh-token hashes
        ├── Redis: temporary failed-login counters
        └── Ed25519 keys: sign and verify access JWTs
```

The service currently exposes these routes:

| Method | Route | Purpose | Authentication |
|--------|-------|---------|----------------|
| `POST` | `/v1/auth/register` | Create an individual account | Email and password |
| `POST` | `/v1/auth/login` | Start a browser/device session | Email and password |
| `GET` | `/v1/auth/me` | Return the current account | Bearer access JWT |
| `POST` | `/v1/auth/refresh` | Rotate the refresh token and issue a new JWT | Refresh cookie and CSRF proof |
| `POST` | `/v1/auth/logout` | End the current browser/device session | Refresh cookie and CSRF proof |
| `POST` | `/v1/auth/logout-all` | End every refresh session for the account | Bearer access JWT |

Health routes are available at `/health/live` and `/health/ready`. Readiness checks that both
PostgreSQL and Redis are usable without returning internal connection details.

## Complete authentication flow

### 1. Registration

```text
Person enters email and password
              │
              ▼
Validate and normalize the email
Validate password length: 15 to 128 characters
              │
              ▼
Hash the password with Argon2id
              │
              ▼
Store the normalized email and password hash in PostgreSQL
              │
              ▼
Return the public account information
```

The original password is never stored. Argon2id creates a one-way hash that can be checked
later but cannot be converted back into the password. Registering the same normalized email
again returns a conflict without exposing database errors.

### 2. Login

```text
Browser                         Authentication service
   │                                      │
   │ Email and password                   │
   ├─────────────────────────────────────►│
   │                                      ├── Verify password hash
   │                                      ├── On failure, update Redis limit
   │                                      ├── On success, clear Redis limit
   │                                      └── Create PostgreSQL session and refresh token
   │                                      │
   │ Access JWT in JSON                   │
   │ Refresh and CSRF cookies             │
   │◄─────────────────────────────────────┤
```

A successful login returns:

```json
{
  "access_token": "signed-jwt-value",
  "token_type": "bearer",
  "expires_in": 900
}
```

It also sets two browser cookies:

- `trialscribe_refresh` contains the refresh token. It is `HttpOnly`, so browser JavaScript
  cannot read it.
- `trialscribe_csrf` contains a signed CSRF value. Browser code can read it and must copy it
  into the `X-CSRF-Token` header for refresh and current-session logout.

Both cookies use `SameSite=Strict`, are restricted to `/v1/auth`, and use `Secure` outside
local development.

### 3. Calling a protected endpoint with the access JWT

The client sends the access token in the HTTP header:

```text
Authorization: Bearer <access-token>
```

For `/v1/auth/me`, the service performs this flow:

```text
Receive access JWT
       │
       ├── Verify the Ed25519 signature
       ├── Require the expected issuer and audience
       ├── Require all identity and time claims
       ├── Confirm type is "access"
       └── Confirm the token is not early or expired
       │
       ▼
Load the active account from PostgreSQL
       │
       ▼
Return public account information
```

The JWT contains an account ID, issuer, audience, issue time, valid-from time, expiration,
unique token ID, and token type. Its payload is readable rather than encrypted. Security
comes from the Ed25519 signature: changing any value makes the signature invalid. Only the
authentication service has the private signing key; other services can later verify tokens
using the public key without gaining permission to create tokens.

### 4. Refreshing a session

An access JWT lasts 900 seconds, or 15 minutes. The refresh session lasts for an absolute
maximum of 30 days, so a browser can obtain another short-lived JWT without resending the
password.

```text
Access JWT expires or is close to expiry
                  │
                  ▼
Browser sends refresh cookie automatically
Browser sends CSRF cookie automatically
Browser copies CSRF value into X-CSRF-Token
                  │
                  ▼
Service checks cookie/header equality and CSRF signature
                  │
                  ▼
Service locks and checks the refresh-token hash in PostgreSQL
                  │
                  ▼
Old refresh token is consumed exactly once
                  │
                  ▼
New access JWT + new refresh cookie + new CSRF cookie
```

The real refresh token is never stored in PostgreSQL. The service stores only its SHA-256
hash. Every successful refresh rotates the token, meaning the old value can never be used
again.

If an already-consumed refresh token is presented again, the service treats that as possible
token theft and revokes that entire browser/device session. Other independent device
sessions remain active.

### 5. Why CSRF protection is required

Browsers attach cookies automatically. Without CSRF protection, a malicious website could
try to make a visitor's browser send a cookie-authenticated request to TrialScribe.

The service therefore requires three matching pieces for refresh and current logout:

```text
HttpOnly refresh cookie
          +
Readable CSRF cookie
          +
X-CSRF-Token request header
          │
          ▼
Cookie values and session-bound signature must be valid
```

Another website may try to trigger a request, but it cannot normally read the TrialScribe
CSRF cookie and place its value in the required custom header. `SameSite=Strict` cookies add
another layer of browser protection.

### 6. Logout behavior

Current-session logout uses the refresh and CSRF cookies:

```text
POST /v1/auth/logout
          │
          ▼
Revoke this browser/device session in PostgreSQL
          │
          ▼
Delete refresh and CSRF cookies
```

Account-wide logout uses an access JWT:

```text
POST /v1/auth/logout-all
Authorization: Bearer <access-token>
          │
          ▼
Revoke every refresh session belonging to the account
          │
          ▼
No device can refresh again without logging in
```

Already-issued access JWTs do not require a database lookup on every request, so they may
remain usable until their 15-minute expiration. Revoked refresh sessions stop working
immediately.

## Redis role

Redis protects the login endpoint from repeated password guessing. It does not store user
accounts, passwords, JWTs, or durable browser sessions.

For each failed login, the service creates a privacy-preserving key from:

```text
normalized email + direct client address + secret HMAC key
```

The HMAC means Redis keys do not expose the email address or client address. The current
fixed window allows five failed attempts in five minutes:

```text
Failed attempts 1–5  → generic 401 response
Failed attempt 6     → 429 Too Many Requests + Retry-After
Five-minute window   → counter expires automatically
Successful login     → matching counter is cleared
```

An unknown email and a wrong password produce the same generic authentication response. The
service also performs a dummy password-hash check for unknown accounts so response timing is
less useful to attackers.

If Redis is unavailable, login fails closed with a safe `503` response. The service does not
allow login without throttling because an attacker could deliberately disrupt Redis to
bypass password-guessing protection. Registration, token verification, and existing access
JWT usage do not use the Redis login counter.

## Data ownership

| Storage | What it contains | What it does not contain |
|---------|------------------|--------------------------|
| PostgreSQL | Accounts, Argon2id password hashes, device sessions, refresh-token hashes, rotation and revocation state | Plaintext passwords, plaintext refresh tokens, CSRF tokens, organization roles |
| Redis | Expiring failed-login counters keyed by HMAC fingerprints | Accounts, password hashes, access JWTs, refresh sessions |
| Browser | Access JWT in application state, protected refresh cookie, readable CSRF cookie | Database password, signing private key |

Organization invitations, memberships, tenant permissions, password reset, email
verification, and enterprise single sign-on are outside this service's current boundary.
The organization/RBAC feature will connect memberships to these global accounts.

## Running locally

From the repository root:

```bash
./scripts.sh env
./scripts.sh install
./scripts.sh auth keys
./scripts.sh infra up
./scripts.sh db migrate
./scripts.sh run auth
```

Open `http://localhost:8001/docs` for the generated API documentation. The complete live
authentication lifecycle can be checked with `./scripts.sh auth test`; it uses an isolated,
destructive test environment and removes its test containers and volumes afterward.

Production deployments must use HTTPS, set `AUTH_COOKIE_SECURE=true`, keep PostgreSQL and
Redis off the public internet, and provide externally managed signing keys, HMAC secrets,
database credentials, and Redis credentials.
