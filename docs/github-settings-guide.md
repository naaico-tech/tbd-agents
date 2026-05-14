# GitHub Settings Guide

This repository uses `master` as the protected/default branch.

## Branch Protection

Apply protection to `master`:

- require pull requests before merging
- require at least one approving review
- dismiss stale approvals when new commits are pushed
- require code owner review
- require status checks before merging
- require branches to be up to date before merging
- disallow force pushes and branch deletion
- optionally restrict direct pushes to maintainers

## CODEOWNERS

`.github/CODEOWNERS` already exists and assigns all paths to `@naaico-tech/maintainers`:

```text
* @naaico-tech/maintainers
```

Do not replace it with placeholder owners.

## Current Workflows

| Workflow | File | Trigger |
|---|---|---|
| Deploy Docs | `.github/workflows/docs.yml` | Pushes to `master` touching docs/MkDocs files, or manual dispatch |
| Integration Tests | `.github/workflows/integration-tests.yml` | Push/PR to `master` touching app/tests/frontend/Docker files, or manual dispatch |
| Publish Docker image to GHCR | `.github/workflows/release.yml` | Published GitHub Release |

Docs are built with `mkdocs build --strict`. Integration tests include Flutter analyze/test/build, Docker build, MongoDB integration tests, unit tests, and PostgreSQL integration tests.

## Actions and Security

Recommended settings:

- allow GitHub Actions and reusable workflows needed by this repo
- require approval for first-time or outside contributors on fork PRs
- grant GitHub Pages permissions for the docs workflow
- enable dependency graph, Dependabot alerts, secret scanning, and push protection
- keep `GITHUB_TOKEN` package write permissions available for release workflow jobs that publish to GHCR
