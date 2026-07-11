FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

# streamlit-ui is a standalone uv project depending on trialscribe-ai via a
# relative path dependency (../../backend/services/ai-engine), so both
# directories must be copied preserving that relative layout.
COPY backend/services/ai-engine backend/services/ai-engine
COPY frontend/streamlit-ui frontend/streamlit-ui

WORKDIR /app/frontend/streamlit-ui

RUN uv sync --frozen

EXPOSE 8501

CMD ["uv", "run", "streamlit", "run", "app.py", "--server.address", "0.0.0.0"]
