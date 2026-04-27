# syntax=docker/dockerfile:1.7

FROM ghcr.io/cirruslabs/flutter:stable AS frontend-builder

WORKDIR /frontend

COPY frontend/pubspec.yaml frontend/pubspec.lock ./
RUN --mount=type=cache,target=/root/.pub-cache \
    flutter config --enable-web && flutter pub get

COPY frontend/ ./
RUN --mount=type=cache,target=/root/.pub-cache \
    flutter build web --release --base-href /dashboard-new-ui/


FROM node:22-bookworm-slim AS node-runtime


FROM python:3.12-slim AS python-builder

WORKDIR /build

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN python - <<'PY'
import pathlib
import tomllib

dependencies = tomllib.loads(pathlib.Path("pyproject.toml").read_text())["project"]["dependencies"]
pathlib.Path("requirements.txt").write_text("\n".join(dependencies) + "\n")
PY
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-compile --prefix=/install -r requirements.txt


FROM python:3.12-slim AS base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/node/bin:${PATH}"

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=python-builder /install /usr/local
COPY --from=node-runtime /usr/local/ /opt/node/
COPY app/ ./app/
COPY --from=frontend-builder /frontend/build/web ./app/dashboard/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
