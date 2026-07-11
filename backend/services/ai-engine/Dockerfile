FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app/backend

# The whole backend/ uv workspace is copied so uv can resolve it
# (workspace root pyproject.toml + lock live at backend/, this service
# is its sole member).
COPY backend/ .

RUN uv sync --frozen --all-packages

EXPOSE 8000

CMD ["uv", "run", "--package", "trialscribe-ai", "uvicorn", "trialscribe_ai.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
