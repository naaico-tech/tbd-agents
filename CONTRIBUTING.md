```
 ██████╗ ██████╗ ███╗   ██╗████████╗██████╗ ██╗██████╗ ██╗   ██╗████████╗██╗███╗   ██╗ ██████╗
██╔════╝██╔═══██╗████╗  ██║╚══██╔══╝██╔══██╗██║██╔══██╗██║   ██║╚══██╔══╝██║████╗  ██║██╔════╝
██║     ██║   ██║██╔██╗ ██║   ██║   ██████╔╝██║██████╔╝██║   ██║   ██║   ██║██╔██╗ ██║██║  ███╗
██║     ██║   ██║██║╚██╗██║   ██║   ██╔══██╗██║██╔══██╗██║   ██║   ██║   ██║██║╚██╗██║██║   ██║
╚██████╗╚██████╔╝██║ ╚████║   ██║   ██║  ██║██║██████╔╝╚██████╔╝   ██║   ██║██║ ╚████║╚██████╔╝
 ╚═════╝ ╚═════╝ ╚═╝  ╚═══╝   ╚═╝   ╚═╝  ╚═╝╚═╝╚═════╝  ╚═════╝    ╚═╝   ╚═╝╚═╝  ╚═══╝ ╚═════╝
```

<p align="center"><sub>⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜</sub></p>

> 🎮 Thank you for your interest in contributing to TBD Agent! This document explains how to get involved.

---

## 🤝 Code of Conduct

Be respectful and constructive. Harassment or abusive behavior will not be tolerated.

---

## 🕹️ How to Contribute

### 🐛 Reporting Issues

- Search [existing issues](../../issues) before opening a new one.
- Use a clear, descriptive title.
- Include steps to reproduce, expected vs actual behavior, and environment details (OS, Python version, Docker version).

### 💡 Suggesting Features

- Open a [feature request issue](../../issues/new) with a clear description of the use case.
- Explain why existing functionality doesn't cover your need.

### 📬 Submitting Pull Requests

```
 ╔════════════════════════════════════════════╗
 ║  ► PR QUEST — FOLLOW THESE STEPS ◄        ║
 ╚════════════════════════════════════════════╝
```

1. 🍴 **Fork** the repository and create a branch from `master`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. 🛠️ **Set up your development environment:**
   ```bash
   # Requires Python 3.12+
   python -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```
   If you are working on `frontend/`, also install Flutter with web support enabled.

3. ✏️ **Make your changes.** Follow the coding standards below.

4. ✅ **Run tests** and ensure they all pass:
   ```bash
   python -m pytest tests/ -v
   ```
   When your change touches `frontend/`, also run:
   ```bash
   cd frontend
   flutter pub get
   flutter analyze
   flutter test
   flutter build web --release --base-href /dashboard/
   ```

5. 🧹 **Run the linter:**
   ```bash
   ruff check app/ tests/
   ```

6. 💾 **Commit** with a clear message:
   ```bash
   git commit -m "feat: add X to Y"
   ```
   Use [Conventional Commits](https://www.conventionalcommits.org/) format:

   ```
    ┌─────────────┬──────────────────────────────────────────────────┐
    │  ░░ PREFIX  │  ░░ MEANING                                      │
    ├─────────────┼──────────────────────────────────────────────────┤
    │  feat:      │  New feature                                      │
    │  fix:       │  Bug fix                                          │
    │  docs:      │  Documentation only                               │
    │  test:      │  Adding or updating tests                         │
    │  refactor:  │  Code change (no fix, no feature)                 │
    │  chore:     │  Maintenance tasks                                │
    └─────────────┴──────────────────────────────────────────────────┘
   ```

7. 🚀 **Push** and open a Pull Request against `master`.

---

## 📏 Coding Standards

```
┌─────────────────────────────────────────────────────────────┐
│  ░░ HOUSE RULES ░░  ·  Keep it clean, keep it sharp         │
└─────────────────────────────────────────────────────────────┘
```

- 🐍 **Python 3.12+** — use modern syntax (type hints, `match` statements where appropriate).
- 🧹 **Formatting & linting** — we use [Ruff](https://docs.astral.sh/ruff/). Run `ruff check` and `ruff format` before committing.
- 🏷️ **Type hints** — all public function signatures should include type annotations.
- ✅ **Tests** — every new feature or bug fix should include tests. We use `pytest` with `pytest-asyncio`.
- ⚡ **Async first** — this is a FastAPI + Motor/Beanie project; prefer `async`/`await` throughout.

---

## 🗂️ Project Structure

```
╔═════════════════════════════════════════════════════════════════════════╗
║                                                                       ║
║  app/                                                                 ║
║  ├── api/routes/     ← FastAPI route handlers                         ║
║  ├── core/           ← Agent engine, event bus, guardrails, registry  ║
║  ├── models/         ← Beanie ODM document models                     ║
║  ├── schemas/        ← Pydantic request/response schemas              ║
║  ├── services/       ← Business logic (auth, MCP, tokens, Copilot)    ║
║  └── tasks/          ← Celery background tasks                        ║
║                                                                       ║
║  tests/              ← Unit tests (mirrors app/ structure)            ║
║  docs/               ← Architecture and feature documentation         ║
║  observability/      ← Grafana dashboards, Prometheus, Loki, Tempo    ║
║                                                                       ║
╚═════════════════════════════════════════════════════════════════════════╝
```

---

## 📋 Pull Request Guidelines

```
┌─────────────────────────────────────────────────────────────┐
│  ░░ PR RULES OF ENGAGEMENT ░░                               │
└─────────────────────────────────────────────────────────────┘
```

- ► Keep PRs focused — one feature or fix per PR.
- ► Include a description of **what** changed and **why**.
- ► Reference related issues (e.g., `Closes #42`).
- ► All CI checks must pass before review.
- ► At least one maintainer approval is required to merge.

---

## 💡 Development Tips

```
┌─────────────────────────────────────────────────────────────┐
│  ░░ PRO TIPS ░░  ·  Level up your dev experience            │
└─────────────────────────────────────────────────────────────┘
```

- 🐳 **Docker Compose** is the fastest way to run the full stack locally:
  ```bash
  docker-compose up --build
  ```
- 📦 **MongoDB, Redis, and observability** services are included in the compose file.
- 🧪 **Flutter dashboard** — the Docker image builds the web bundle and FastAPI serves it at `/dashboard`; use `/dashboard-legacy` to verify the legacy UI.
- 📖 See [docs/getting-started/local-setup.md](docs/getting-started/local-setup.md) for bare-metal setup.

---

## 📜 License

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).

---

<p align="center">⬛⬜⬛ <a href="https://www.naaico.com"><strong>NAAICO</strong></a> ⬛⬜⬛</p>
