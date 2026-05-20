# syntax=docker/dockerfile:1.7
# Node 20 — Node 25 is hard-blocked upstream (V8 WASM JIT bug with tree-sitter)
FROM node:20-bookworm-slim

WORKDIR /app

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
        git \
    && rm -rf /var/lib/apt/lists/*

# Install codegraph CLI globally (pinned version)
RUN npm install -g @colbymchenry/codegraph@0.7.12

# Install app dependencies
COPY package*.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --omit=dev

COPY src/ ./src/

ENV PORT=3001 \
    HOST=0.0.0.0 \
    WORKSPACE=/opt/codegraph_repos \
    NODE_ENV=production

EXPOSE 3001

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD node -e "require('http').get('http://localhost:3001/health', r => process.exit(r.statusCode === 200 ? 0 : 1)).on('error', () => process.exit(1))"

CMD ["node", "src/index.js"]
