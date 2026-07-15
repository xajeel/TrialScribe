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
- migrate: n/a

> Repos: single service-oriented monorepo; backend services are separate uv workspace packages, the React client is an npm project, and the interim Streamlit UI remains a standalone uv project.
