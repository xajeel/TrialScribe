FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

# Whole workspace is copied because uv needs every member's pyproject.toml to
# resolve the monorepo, and this single image serves both the ai-engine API
# and the interim Streamlit UI (selected via docker-compose's `command:`).
COPY pyproject.toml uv.lock .python-version ./
COPY backend/services/ai-engine backend/services/ai-engine
COPY frontend/streamlit-ui frontend/streamlit-ui

RUN uv sync --frozen --all-packages

EXPOSE 8000 8501

CMD ["uv", "run", "--package", "trialscribe-ai", "uvicorn", "trialscribe_ai.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
