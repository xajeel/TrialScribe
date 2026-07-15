# Roadmap — TrialScribe

| # | Feature | Needs | Status |
|---|---------|-------|--------|
| 1 | platform-skeleton | — | done |
| 2 | local-runtime-infrastructure | 1 | todo |
| 3 | postgres-data-foundation | 2 | todo |
| 4 | user-authentication | 3 | todo |
| 5 | organization-rbac | 4 | todo |
| 6 | api-gateway | 2, 4, 5 | todo |
| 7 | conversation-workspaces | 3, 5, 6 | todo |
| 8 | document-ingestion | 3, 5, 7 | todo |
| 9 | rag-indexing-retrieval | 2, 8 | todo |
| 10 | web-research-evidence | 8, 9 | todo |
| 11 | kafka-event-backbone | 2, 5 | todo |
| 12 | background-job-runtime | 7, 11 | todo |
| 13 | m11-section-workspace | 7 | todo |
| 14 | citation-backed-section-generation | 9, 10, 12, 13 | todo |
| 15 | section-revision-and-approval | 14 | todo |
| 16 | react-application-shell | 4, 5, 6 | todo |
| 17 | three-pane-authoring-workspace | 7, 8, 13, 16 | todo |
| 18 | generation-progress-and-sources | 14, 17 | todo |
| 19 | conversation-cost-tracking | 14, 17 | todo |
| 20 | docx-protocol-export | 15 | todo |
| 21 | prometheus-grafana-observability | 6, 11, 12, 14 | todo |
| 22 | security-and-resilience-hardening | 8, 12, 18, 21 | todo |
| 23 | compose-release-and-scale-validation | 19, 20, 21, 22 | todo |

## V1 decisions

- Local email/password accounts with access and refresh tokens; enterprise SSO is deferred.
- Multi-tenant organizations require strict organization-scoped data access and RBAC.
- Docker Compose is the only deployment target, including the production-style release profile.
- Capacity target: 500 concurrent users and 10,000 protocol-generation jobs per day on documented reference hardware.

## 1. platform-skeleton
Goal: Establish a consistent service-oriented monorepo that can grow without coupling service releases.
Scope:
- Define independently runnable boundaries for gateway, auth, user, AI, worker, and React applications.
- Standardize root install, run, lint, test, and configuration workflows.
- Give every backend service liveness and readiness behavior.
Done when:
- A clean checkout completes install, lint, and baseline test commands successfully.
- Automated smoke tests start each application boundary and receive healthy responses.

## 2. local-runtime-infrastructure
Goal: Provide the complete local data and messaging runtime through Docker Compose.
Scope:
- Run PostgreSQL with pgvector, Redis, and Kafka-compatible messaging locally.
- Persist state across normal container restarts and isolate test data from development data.
- Expose dependency readiness so applications wait for usable infrastructure.
Done when:
- The infrastructure profile reaches healthy state from a clean machine with one command.
- Integration checks prove database, vector, Redis, and Kafka read/write connectivity.

## 3. postgres-data-foundation
Goal: Create a durable relational foundation shared by all persistent product capabilities.
Scope:
- Establish versioned migrations and consistent database lifecycle conventions.
- Support transactional service persistence and organization-scoped records.
- Enable pgvector as part of repeatable database initialization.
Done when:
- Automated tests migrate both an empty database and the previous migration state to current.
- Restart tests prove committed records and vector capability remain available.

## 4. user-authentication
Goal: Secure the product with production-grade local account authentication.
Scope:
- Support account creation or invitation, login, logout, and current-user lookup.
- Issue short-lived access tokens and rotated, revocable refresh tokens.
- Protect credentials with secure password handling and abuse-resistant responses.
Done when:
- Authentication tests prove valid login and refresh while invalid credentials return 401 without account leakage.
- Revoked, expired, replayed, and tampered tokens are rejected by automated tests.

## 5. organization-rbac
Goal: Isolate every user's data by organization and enforce role-based permissions.
Scope:
- Support organizations, memberships, and defined administrator and authoring roles.
- Apply tenant scope to all protected data access and service requests.
- Allow authorized membership management without exposing another organization.
Done when:
- An automated permission matrix proves each role can perform only its allowed operations.
- Cross-organization access tests return no protected data for every persistent resource.

## 6. api-gateway
Goal: Give the frontend one secure and stable entry point to backend services.
Scope:
- Route versioned API requests to auth, user, AI, and job capabilities.
- Validate authentication and propagate trusted identity and organization context.
- Provide consistent request IDs, errors, CORS behavior, and service availability responses.
Done when:
- Gateway contract tests route every public endpoint and reject protected anonymous requests with 401.
- A traced integration request retains one correlation ID across all participating services.

## 7. conversation-workspaces
Goal: Let users create, list, open, rename, and resume multiple durable authoring conversations.
Scope:
- Persist conversation ownership, title, activity state, and organization scope.
- Preserve message and authoring context across logout, restart, and later resume.
- Support pagination and safe conversation deletion or archival.
Done when:
- Integration tests create multiple conversations and resume each with its original context after restart.
- Users cannot list, open, modify, or delete conversations outside their organization.

## 8. document-ingestion
Goal: Safely attach trial JSON and research documents to an individual conversation.
Scope:
- Validate and ingest structured trial data plus supported research document formats.
- Record durable document metadata, source identity, processing state, and conversation ownership.
- Support listing, retrieval, failure reporting, and removal of uploaded sources.
Done when:
- Fixture tests accept valid trial JSON and documents while rejecting malformed, oversized, or unsupported uploads.
- Uploaded-source metadata and content remain correctly scoped and available after restart.

## 9. rag-indexing-retrieval
Goal: Turn uploaded evidence into tenant-safe, citation-ready retrieval using PostgreSQL and pgvector.
Scope:
- Extract, normalize, chunk, embed, and index supported conversation sources.
- Retrieve relevant passages only from the requesting conversation and organization.
- Preserve stable provenance from every chunk back to its source and location.
Done when:
- Retrieval tests return expected passages and stable source identifiers for known fixtures.
- Cross-conversation and cross-organization retrieval tests return no foreign evidence.

## 10. web-research-evidence
Goal: Add trustworthy online research as a first-class evidence source for section writing.
Scope:
- Research PubMed and configured trusted websites for a requested M11 section.
- Normalize, deduplicate, and store web evidence with URL, title, date, and retrieval provenance.
- Make external failures bounded, retryable, and visible without losing uploaded evidence.
Done when:
- Recorded-source tests produce deduplicated evidence with resolvable provenance for each result.
- Allow-list and failure-path tests reject untrusted sources and return a controlled partial result.

## 11. kafka-event-backbone
Goal: Decouple backend services through reliable, versioned Kafka event contracts.
Scope:
- Define shared event identity, tenant context, versioning, correlation, and causation behavior.
- Publish and consume lifecycle events without relying on synchronous service internals.
- Handle duplicate, invalid, and unprocessable events through explicit recovery paths.
Done when:
- Contract tests prove compatible publish and consume behavior between participating services.
- Integration tests prove duplicate handling and failed-event recovery without duplicate effects.

## 12. background-job-runtime
Goal: Run long AI and ingestion work outside API request cycles with observable job state.
Scope:
- Queue tenant-scoped jobs through Kafka and execute them in independently scalable workers.
- Track queued, running, progress, succeeded, failed, cancelled, and retrying states through Redis-backed coordination.
- Make retries idempotent and recover work safely after worker interruption.
Done when:
- API integration tests return promptly while workers complete jobs and expose monotonic progress.
- Restart, retry, cancellation, and duplicate-delivery tests produce one durable outcome per job.

## 13. m11-section-workspace
Goal: Model an ICH M11 protocol as ordered sections with durable authoring state.
Scope:
- Provide the supported M11 section catalog, titles, ordering, and conversation selection.
- Store per-section instructions, draft content, status, and revision history.
- Distinguish editable drafts from sections explicitly marked done.
Done when:
- Tests create an ordered section workspace and preserve every section state after restart.
- State-transition tests enforce valid draft, revision, done, and reopen behavior.

## 14. citation-backed-section-generation
Goal: Draft requested M11 sections from trial JSON, uploaded documents, and online evidence with citations.
Scope:
- Adapt the existing AI workflow to generate one or more requested sections asynchronously.
- Ground claims in retrieved evidence and attach stable source references to generated content.
- Persist partial successes, model metadata, prompts, and controlled failure information.
Done when:
- End-to-end fixture generation produces the requested M11 sections and every citation resolves to stored evidence.
- A failed section can be retried without duplicating successful sections or corrupting conversation state.

## 15. section-revision-and-approval
Goal: Let users refine complete sections or selected text while preserving accepted work.
Scope:
- Rewrite a whole section from new instructions or rewrite a selected passage using offered options.
- Support direct editing, revision history, comparison, and restoration of earlier content.
- Persist sections marked done while other sections continue changing.
Done when:
- End-to-end tests cover whole-section rewrite, selection rewrite, option choice, edit, restore, and mark-done flows.
- Done sections remain byte-stable through unrelated generation until explicitly reopened.

## 16. react-application-shell
Goal: Establish the production React frontend with authenticated routing and reliable API integration.
Scope:
- Provide login, logout, session refresh, organization context, and protected navigation.
- Standardize API state, loading, empty, retry, and safe error experiences.
- Establish accessible responsive layout and frontend test conventions.
Done when:
- Frontend type-check, lint, unit test, and production build commands pass.
- Browser tests prove login, refresh, protected-route rejection, logout, and expired-session recovery.

## 17. three-pane-authoring-workspace
Goal: Deliver the ChatGPT-like conversation and section-authoring interface.
Scope:
- Show resumable conversations in the left pane and instructions plus section content in the center.
- Split the right pane into a scrollable document list and M11 section-title list.
- Open full section content in a modal and expose upload and conversation actions in context.
Done when:
- Browser tests create, switch, and resume conversations without mixing their documents or sections.
- UI tests verify all three panes, scrolling areas, upload feedback, and full-section modal behavior.

## 18. generation-progress-and-sources
Goal: Make asynchronous writing progress and evidence transparent in the authoring interface.
Scope:
- Display job progress, per-section state, retryable failures, cancellation, and completion.
- Render citations within section text and distinguish uploaded, trial-data, and internet sources.
- Open source details and the cited passage without losing the current editing context.
Done when:
- Browser tests observe queued-to-complete progress and recover correctly from a failed section.
- Every rendered fixture citation opens the matching source metadata and cited evidence passage.

## 19. conversation-cost-tracking
Goal: Show accurate cumulative LLM usage and cost for every conversation.
Scope:
- Attribute model, token, and cost usage to jobs, sections, conversations, users, and organizations.
- Display a durable conversation total and generation-level breakdown in the React interface.
- Correlate optional LangSmith traces without making external tracing the cost source of record.
Done when:
- Deterministic usage fixtures produce exact per-call and conversation totals under versioned model pricing.
- Browser tests prove totals survive resume and cannot reveal another organization's usage.

## 20. docx-protocol-export
Goal: Assemble completed sections into a downloadable, traceable ICH M11 DOCX document.
Scope:
- Export done sections in M11 order with headings, citations, references, and document metadata.
- Keep unfinished sections out unless the user explicitly requests a clearly marked draft export.
- Store export status and make completed files available only to authorized conversation members.
Done when:
- Automated document inspection proves expected ordering, headings, section text, and reference entries.
- Browser tests request, download, and open an authorized export while forbidden access is rejected.

## 21. prometheus-grafana-observability
Goal: Make service health, errors, latency, throughput, dependencies, and AI jobs observable locally.
Scope:
- Expose Prometheus metrics from every backend service with safe, bounded labels.
- Scrape services and infrastructure and provision useful Grafana dashboards automatically.
- Correlate structured errors, requests, Kafka events, workers, and generation jobs.
Done when:
- Prometheus target tests show every service healthy and required metric families present.
- Induced API, worker, Kafka, database, and AI failures appear on provisioned Grafana views.

## 22. security-and-resilience-hardening
Goal: Close cross-service security and failure-mode gaps before the release profile is accepted.
Scope:
- Enforce upload safety, tenant isolation, least privilege, rate limits, secure headers, and secret handling.
- Add timeouts, bounded retries, graceful shutdown, dependency degradation, and recovery behavior.
- Protect sensitive clinical, document, credential, prompt, and evidence data from logs and error responses.
Done when:
- Automated security tests cover authorization bypass, tenant leakage, malicious uploads, token abuse, CORS, and rate limits.
- Failure tests prove controlled degradation and recovery without lost done sections or duplicate jobs.

## 23. compose-release-and-scale-validation
Goal: Deliver a reproducible Docker Compose release and validate the agreed v1 capacity target.
Scope:
- Provide a release profile with health gates, migrations, persistence, resource bounds, and restart policies.
- Document backup, restore, upgrade, rollback, operations, and reference hardware expectations.
- Validate 500 concurrent users and 10,000 daily job equivalents with controlled provider substitutes.
Done when:
- A clean host starts the full platform and passes smoke, backup/restore, restart, and upgrade checks.
- Repeatable load tests meet documented latency, error-rate, queue-drain, and resource thresholds at target capacity.

## Out of v1

- Enterprise OIDC/SAML SSO and identity-provider provisioning.
- Kubernetes, cloud-managed services, multi-region deployment, and active-active availability.
- Real-time multi-user co-authoring, comments, and formal reviewer approval workflows.
- Advanced enterprise administration, audit export, legal hold, retention policy, and compliance certification.
- Native mobile applications and protocol templates other than ICH M11.
- The interim Streamlit interface as a supported production frontend.
