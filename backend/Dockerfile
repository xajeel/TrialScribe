FROM python:3.12.3-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.10.7 /uv /usr/local/bin/uv

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin trialscribe

WORKDIR /app/backend

COPY . .

RUN uv sync --frozen --all-packages --no-dev \
    || uv sync --frozen --all-packages --no-dev \
    || uv sync --frozen --all-packages --no-dev \
    && chown -R trialscribe:trialscribe /app

USER trialscribe

ENV PATH="/app/backend/.venv/bin:$PATH"
