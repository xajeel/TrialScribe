.PHONY: sync api ui lint test up

sync:
	uv sync --all-packages

api:
	uv run --package trialscribe-ai uvicorn trialscribe_ai.api.app:app --reload

ui:
	uv run --package trialscribe-streamlit streamlit run frontend/streamlit-ui/app.py

lint:
	uv run ruff check .

test:
	uv run --package trialscribe-ai pytest backend/services/ai-engine/tests/

up:
	docker compose up --build
