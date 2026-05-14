# Local Setup

This root-level page is kept for older links. The maintained local development guide is:

[:octicons-arrow-right-24: Getting Started: Local Setup](getting-started/local-setup.md)

Current highlights:

- Use `docker compose up --build` or `docker compose up` depending on whether you are building locally or using registry images.
- The Flutter dashboard is served at `/dashboard` with build base href `/dashboard/`.
- The legacy UI is `/dashboard-legacy`; `/dashboard-new-ui` is only a compatibility alias.
- `SESSION_TIMEOUT` defaults to `600` seconds.
- `.env.example` defaults to `COMPOSE_PROFILES=qdrant`, `DB_BACKEND=mongo`, and MongoDB database `copilot_agent_hub`.
