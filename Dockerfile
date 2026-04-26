FROM ghcr.io/cirruslabs/flutter:stable AS frontend-builder

WORKDIR /frontend

COPY frontend/pubspec.yaml frontend/pubspec.lock ./
RUN flutter config --enable-web && flutter pub get

COPY frontend/ ./
RUN flutter build web --release --base-href /dashboard-new-ui/


FROM python:3.12-slim AS base

WORKDIR /app

# Install system deps + Node.js 22 (required for npx-based MCP servers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl git \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app/ ./app/
RUN pip install --no-cache-dir .
COPY --from=frontend-builder /frontend/build/web ./app/dashboard/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
