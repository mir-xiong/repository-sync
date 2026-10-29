FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    DATA_DIR=/data \
    PATH="/app/backend/.venv/bin:${PATH}" \
    GIT_CONFIG_COUNT=1 \
    GIT_CONFIG_KEY_0=safe.directory \
    GIT_CONFIG_VALUE_0=*

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git util-linux \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 --shell /bin/bash app \
    && mkdir -p /data /mirrors \
    && chown app:app /data /mirrors

WORKDIR /app/backend

COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY backend/app ./app
COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
