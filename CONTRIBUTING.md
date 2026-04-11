# Contributing to Copilot Agent Hub

Thank you for your interest in contributing! This document explains how to get involved.

## Code of Conduct

Be respectful and constructive. Harassment or abusive behavior will not be tolerated.

## How to Contribute

### Reporting Issues

- Search [existing issues](../../issues) before opening a new one.
- Use a clear, descriptive title.
- Include steps to reproduce, expected vs actual behavior, and environment details (OS, Python version, Docker version).

### Suggesting Features

- Open a [feature request issue](../../issues/new) with a clear description of the use case.
- Explain why existing functionality doesn't cover your need.

### Submitting Pull Requests

1. **Fork** the repository and create a branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Set up your development environment:**
   ```bash
   # Requires Python 3.12+
   python -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

3. **Make your changes.** Follow the coding standards below.

4. **Run tests** and ensure they all pass:
   ```bash
   python -m pytest tests/ -v
   ```

5. **Run the linter:**
   ```bash
   ruff check app/ tests/
   ```

6. **Commit** with a clear message:
   ```bash
   git commit -m "feat: add X to Y"
   ```
   Use [Conventional Commits](https://www.conventionalcommits.org/) format:
   - `feat:` new feature
   - `fix:` bug fix
   - `docs:` documentation only
   - `test:` adding or updating tests
   - `refactor:` code change that neither fixes a bug nor adds a feature
   - `chore:` maintenance tasks

7. **Push** and open a Pull Request against `main`.

## Coding Standards

- **Python 3.12+** — use modern syntax (type hints, `match` statements where appropriate).
- **Formatting & linting** — we use [Ruff](https://docs.astral.sh/ruff/). Run `ruff check` and `ruff format` before committing.
- **Type hints** — all public function signatures should include type annotations.
- **Tests** — every new feature or bug fix should include tests. We use `pytest` with `pytest-asyncio`.
- **Async first** — this is a FastAPI + Motor/Beanie project; prefer `async`/`await` throughout.

## Project Structure

```
app/
├── api/routes/     # FastAPI route handlers
├── core/           # Agent engine, event bus, guardrails, tool registry
├── models/         # Beanie ODM document models
├── schemas/        # Pydantic request/response schemas
├── services/       # Business logic (auth, MCP, tokens, Copilot client)
└── tasks/          # Celery background tasks
tests/              # Unit tests (mirrors app/ structure)
docs/               # Architecture and feature documentation
observability/      # Grafana dashboards, Prometheus, Loki, Tempo configs
```

## Pull Request Guidelines

- Keep PRs focused — one feature or fix per PR.
- Include a description of **what** changed and **why**.
- Reference related issues (e.g., `Closes #42`).
- All CI checks must pass before review.
- At least one maintainer approval is required to merge.

## Development Tips

- **Docker Compose** is the fastest way to run the full stack locally:
  ```bash
  docker-compose up --build
  ```
- **MongoDB, Redis, and observability** services are included in the compose file.
- See [docs/local-setup.md](docs/local-setup.md) for bare-metal setup.

## License

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).
