# Release vX.Y.Z — YYYY-MM-DD

<!-- Replace vX.Y.Z with the version tag and fill in all sections below.     -->
<!-- Delete any section that is not applicable for this release.              -->

---

## Summary

<!-- 1–3 sentence high-level description of what this release delivers.
     What problem does it solve? Who benefits? Is it a patch, minor, or major? -->

> _e.g., This minor release introduces scheduled agent support and improves SSE reliability under high concurrency._

---

## What's New

<!-- List every new feature, capability, or user-visible improvement added
     in this release. Link to relevant PRs or documentation where helpful. -->

- **Feature name** — Brief description of what it does and why it matters. (#PR)
- **Feature name** — Brief description. (#PR)

---

## Bug Fixes

<!-- List every bug that was fixed. Include the symptom, not just the internal
     ticket number. Helps users confirm their issue is resolved. -->

- Fixed `<symptom>` that occurred when `<condition>`. (#PR / issue #N)
- Fixed `<symptom>`. (#PR)

---

## Breaking Changes

<!-- List any changes that require action from operators or API consumers.
     If there are none, write "None." — do NOT delete this section. -->

None.

<!--
Examples of breaking changes to document:
- Renamed environment variable `OLD_VAR` → `NEW_VAR`. Update your `.env` files.
- Endpoint `GET /api/v1/foo` removed; use `GET /api/v2/foo` instead.
- Minimum Python version raised to 3.13.
-->

---

## Upgrade Notes

<!-- Step-by-step instructions for upgrading from the previous version.
     Include Docker Compose, Helm, and local dev instructions where relevant.
     Reference the migration guide for any required schema changes. -->

### Docker Compose

```bash
docker compose pull
docker compose down
docker compose up -d
```

### Helm

```bash
helm upgrade tbd-agents ./helm/tbd-agents \
  --set image.tag=X.Y.Z \
  --reuse-values

kubectl rollout status deployment/tbd-agents
```

### Local Development

```bash
git pull origin master
uv sync
```

### Database Migrations

<!-- List any manual migration steps needed. If none, write "No migration required." -->

No migration required.

---

## Full Changelog

**Full diff:** [`vPREV...vX.Y.Z`](https://github.com/naaico-tech/tbd-agents/compare/vPREV...vX.Y.Z)

See [CHANGELOG.md](https://github.com/naaico-tech/tbd-agents/blob/master/CHANGELOG.md) for the complete history.
