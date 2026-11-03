# Every Python app's image: PACKAGE picks the workspace member (pagerwise-api, -consumer, -indexer, -simulator,
# -docs-mock), COMMAND its default command (the api image also runs the triage worker: pagerwise_api.worker).
# RUNTIME is the models image for apps that embed or rerank, plain Python otherwise.
ARG RUNTIME=python:3.13-slim-trixie@sha256:ae14d4ce8771606477a81446e7ef429edd6762305fc50c84507c1041fa8285d1

FROM python:3.13-slim-trixie@sha256:ae14d4ce8771606477a81446e7ef429edd6762305fc50c84507c1041fa8285d1 AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 /uv /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0 UV_NO_DEV=1
WORKDIR /app
ARG PACKAGE
# Workspace members install editable: the apps find data/ and alembic.ini relative to their source, so /app keeps
# the repository's layout.
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv test -n "$PACKAGE" && uv sync --frozen --package "$PACKAGE"

FROM ${RUNTIME}
RUN useradd --system --uid 10001 --no-create-home app
COPY --from=build /app /app
WORKDIR /app
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1
USER app
ARG COMMAND
ENV APP_COMMAND=${COMMAND}
CMD exec $APP_COMMAND
