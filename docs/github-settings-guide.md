# GitHub Repository Settings Guide

This guide walks you through configuring your GitHub repository for open source with controlled access — maintainers decide who can contribute and collaborate.

---

## 1. General Settings

**Settings → General**

| Setting | Recommended Value | Why |
|---|---|---|
| Visibility | **Public** | Required for open source |
| Features → Issues | **Enabled** | Community bug reports and feature requests |
| Features → Projects | **Enabled** | Optional; useful for roadmap tracking |
| Features → Discussions | **Enabled** | Community Q&A without cluttering issues |
| Features → Wiki | **Disabled** | Use `docs/` folder instead for version-controlled documentation |

---

## 2. Branch Protection Rules

**Settings → Branches → Add rule**

Apply to branch pattern: `main`

| Rule | Setting | Why |
|---|---|---|
| Require a pull request before merging | **Enabled** | No direct pushes to main |
| Required approving reviews | **1** (minimum) | Maintainer review before merge |
| Dismiss stale pull request approvals | **Enabled** | Re-review after new commits |
| Require review from code owners | **Enabled** | Route reviews to the right people |
| Require status checks to pass | **Enabled** | Tests must pass before merge |
| Require branches to be up to date | **Enabled** | PRs must be rebased on latest main |
| Restrict who can push | **Enabled** | Only maintainers can push directly |
| Include administrators | **Enabled** | Rules apply to everyone, no exceptions |
| Allow force pushes | **Disabled** | Protect commit history |
| Allow deletions | **Disabled** | Prevent accidental branch deletion |

---

## 3. CODEOWNERS

Create a `.github/CODEOWNERS` file to auto-assign reviewers:

```
# Default owners for everything
* @your-github-username

# Specific paths (optional)
# app/core/     @core-team
# docs/         @docs-team
# observability/ @platform-team
```

When a PR touches files matching a pattern, the specified owners are automatically requested for review.

---

## 4. Collaborator & Contributor Access

**Settings → Collaborators and teams**

### Roles

| Role | Access Level | Who Gets This |
|---|---|---|
| **Read** | View code, open issues | General public (automatic for public repos) |
| **Triage** | Manage issues and PRs, no code push | Community moderators |
| **Write** | Push to non-protected branches | Trusted contributors |
| **Maintain** | Manage repo settings (no destructive actions) | Core team members |
| **Admin** | Full control | Repository owners only |

### Strategy for Controlled Open Source

1. **Do not** grant Write access broadly. Contributors fork the repo and open PRs.
2. Invite proven contributors as **Write** collaborators only after consistent quality contributions.
3. Keep **Admin** access to 1–2 owners maximum.
4. Use **teams** (in an organization) to manage groups efficiently.

---

## 5. Fork Workflow (How External Contributors Work)

Since the repo is public, anyone can:

1. **Fork** the repository to their account
2. Create a branch and make changes
3. Open a **Pull Request** back to your `main` branch
4. Wait for your review and CI checks

You (maintainers) control:
- Whether the PR gets reviewed
- Whether it passes required checks
- Whether it gets merged

**No one outside your collaborator list can push directly to your repo.**

---

## 6. Actions & CI

**Settings → Actions → General**

| Setting | Value |
|---|---|
| Actions permissions | **Allow select actions and reusable workflows** |
| Fork pull request workflows | **Require approval for first-time contributors** |
| Fork pull request workflows | **Require approval for all outside collaborators** (more secure) |

Recommended CI workflow (`.github/workflows/ci.yml`):

```yaml
name: CI
on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: ruff check app/ tests/
      - run: pytest tests/ -v
```

---

## 7. Security Settings

**Settings → Code security and analysis**

| Feature | Setting |
|---|---|
| Dependency graph | **Enabled** |
| Dependabot alerts | **Enabled** |
| Dependabot security updates | **Enabled** |
| Secret scanning | **Enabled** |
| Secret scanning push protection | **Enabled** |

---

## 8. Issue & PR Templates

Create `.github/ISSUE_TEMPLATE/bug_report.md`:

```markdown
---
name: Bug Report
about: Report a bug
labels: bug
---

**Describe the bug**

**Steps to reproduce**

**Expected behavior**

**Environment**
- OS:
- Python version:
- Docker version:
```

Create `.github/PULL_REQUEST_TEMPLATE.md`:

```markdown
## What does this PR do?

## Related issue

Closes #

## Checklist
- [ ] Tests added/updated
- [ ] Linter passes (`ruff check`)
- [ ] Documentation updated (if applicable)
```

---

## 9. Tags & Releases

Use [Semantic Versioning](https://semver.org/):

```bash
git tag -a v0.2.0 -m "Release v0.2.0"
git push origin v0.2.0
```

Create a GitHub Release from the tag with a changelog summarizing what changed.

---

## Summary Checklist

- [ ] Repository set to **Public**
- [ ] Branch protection on `main` with required reviews and status checks
- [ ] `CODEOWNERS` file created
- [ ] Collaborator roles assigned (Admin only for owners)
- [ ] GitHub Actions CI workflow added
- [ ] Security features enabled (Dependabot, secret scanning)
- [ ] Issue and PR templates created
- [ ] `LICENSE` (Apache 2.0) exists
- [ ] `CONTRIBUTING.md` exists
- [ ] `README.md` has contributing and license sections
