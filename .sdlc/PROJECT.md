# TrialScribe
AI-powered clinical research assistant for drafting citation-backed ICH M11 clinical trial protocol sections.

## Stack
Python 3.12, FastAPI, LangGraph/LangChain, Pydantic, Streamlit, uv, Node.js, React, TypeScript, Vite, and npm; exact versions are pinned in CRAFT.md.

## Commands
- install: `./scripts.sh install`
- env: `./scripts.sh env`
- test: `./scripts.sh test`
- lint: `./scripts.sh lint`
- smoke: `./scripts.sh smoke`
- run: `./scripts.sh run <gateway|auth|user|ai|worker|web>`
- compose: `./scripts.sh up`
- migrate: `./scripts.sh db migrate`
- migration-status: `./scripts.sh db current`
- database-test: `./scripts.sh db test`
- authentication-keys: `./scripts.sh auth keys`
- authentication-test: `./scripts.sh auth test`
- organization-rbac-test: `./scripts.sh user test`

> Repos: single service-oriented monorepo; backend services are separate uv workspace packages, the React client is an npm project, and the interim Streamlit UI remains a standalone uv project.
