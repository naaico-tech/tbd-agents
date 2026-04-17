# Roadmap

> Project direction and milestone tracking for TBD Agents.
> Each milestone links to a GitHub milestone and its tracking epic.

## Milestone Overview

| Milestone | Status | Epic |
|-----------|--------|------|
| [M1: Claude SDK Support](https://github.com/naaico-tech/tbd-agents/milestone/1) | ✅ Complete | [#7](https://github.com/naaico-tech/tbd-agents/issues/7) |
| [M2: In-House Memory Support](https://github.com/naaico-tech/tbd-agents/milestone/2) | 🔧 In Progress | [#15](https://github.com/naaico-tech/tbd-agents/issues/15) |
| [M3: BYOK Provider Parity](https://github.com/naaico-tech/tbd-agents/milestone/3) | 🔧 In Progress | [#24](https://github.com/naaico-tech/tbd-agents/issues/24) |
| [M4: Integration Test Coverage](https://github.com/naaico-tech/tbd-agents/milestone/4) | 🔧 In Progress | [#33](https://github.com/naaico-tech/tbd-agents/issues/33) |
| [M5: Platform Hardening](https://github.com/naaico-tech/tbd-agents/milestone/5) | 📋 Planned | [#44](https://github.com/naaico-tech/tbd-agents/issues/44) |

---

## M1: Claude SDK Support ✅

Add Anthropic Claude as an alternative execution backend alongside the GitHub Copilot SDK.

- Add `anthropic` Python SDK dependency
- Implement Claude SDK client builder
- Add Claude execution path in `agent_engine`
- Map MCP tool definitions to Claude tool format
- Handle Claude-specific streaming events
- Add unit tests and documentation

## M2: In-House Memory Support 🔧

Replace external memory MCP servers with a built-in memory layer backed by PostgreSQL.

- Design memory data model
- Implement memory manager and STM services
- Build memory CRUD API routes
- Add memory write-back from agent responses
- Add unit tests and documentation

## M3: BYOK Provider Parity 🔧

Bring Your Own Key providers to feature parity with the Copilot SDK path.

- Add streaming support for BYOK providers
- Implement context compaction
- Normalize usage tracking across providers
- Add progress/todo tracking for BYOK executions
- Add retry and error handling parity
- Support Azure OpenAI deployment-specific routing
- Add SDK selection config and env-level runtime override
- Route Copilot SDK BYOK through ProviderConfig for Anthropic keys
- Add unit tests and documentation

## M4: Integration Test Coverage 🔧

End-to-end integration tests covering core execution paths.

- Set up integration test infrastructure
- Test full agent execution loop (Copilot SDK & BYOK paths)
- Test SSE streaming end-to-end
- Test MCP tool invocation flows
- Test guardrail enforcement end-to-end
- Test knowledge injection flow
- Test repo sync operations
- Test Celery task lifecycle
- Add CI pipeline for integration tests

## M5: Platform Hardening 📋

Stability, resilience, and documentation improvements for production readiness.

- Improve SSE reconnection handling
- Enhance knowledge base documentation
- Add output guardrails for post-execution validation
- Add migration and upgrade guide
- Add ROADMAP.md *(this file)*

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to get involved. Open issues on the
[issue tracker](https://github.com/naaico-tech/tbd-agents/issues) are a great
place to start.
