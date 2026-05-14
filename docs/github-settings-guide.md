```
 ██████╗ ██╗████████╗██╗  ██╗██╗   ██╗██████╗     ███████╗███████╗████████╗████████╗██╗███╗   ██╗ ██████╗ ███████╗
██╔════╝ ██║╚══██╔══╝██║  ██║██║   ██║██╔══██╗    ██╔════╝██╔════╝╚══██╔══╝╚══██╔══╝██║████╗  ██║██╔════╝ ██╔════╝
██║  ███╗██║   ██║   ███████║██║   ██║██████╔╝    ███████╗█████╗     ██║      ██║   ██║██╔██╗ ██║██║  ███╗███████╗
██║   ██║██║   ██║   ██╔══██║██║   ██║██╔══██╗    ╚════██║██╔══╝     ██║      ██║   ██║██║╚██╗██║██║   ██║╚════██║
╚██████╔╝██║   ██║   ██║  ██║╚██████╔╝██████╔╝    ███████║███████╗   ██║      ██║   ██║██║ ╚████║╚██████╔╝███████║
 ╚═════╝ ╚═╝   ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚═════╝     ╚══════╝╚══════╝   ╚═╝      ╚═╝   ╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚══════╝
```

<p align="center"><sub>⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜⬛⬜</sub></p>

> 🔒 This guide walks you through configuring your GitHub repository for open source with controlled access — maintainers decide who can contribute and collaborate.

---

## 1️⃣ General Settings

```
┌─────────────────────────────────────────────────────────────┐
│  ░░ SETTINGS → GENERAL ░░                                   │
└─────────────────────────────────────────────────────────────┘
```

```
 ┌──────────────────────────┬──────────────┬──────────────────────────────────────────────┐
 │  ░░ SETTING              │  ░░ VALUE    │  ░░ WHY                                      │
 ├──────────────────────────┼──────────────┼──────────────────────────────────────────────┤
 │  Visibility              │  Public      │  Required for open source                    │
 │  Features → Issues       │  Enabled     │  Community bug reports and feature requests   │
 │  Features → Projects     │  Enabled     │  Optional; useful for roadmap tracking        │
 │  Features → Discussions  │  Enabled     │  Community Q&A without cluttering issues      │
 │  Features → Wiki         │  Disabled    │  Use docs/ folder for version-controlled docs │
 └──────────────────────────┴──────────────┴──────────────────────────────────────────────┘
```

---

## 2️⃣ Branch Protection Rules

```
┌─────────────────────────────────────────────────────────────┐
│  ░░ SETTINGS → BRANCHES → ADD RULE ░░  (apply to: main)    │
└─────────────────────────────────────────────────────────────┘
```

```
 ┌────────────────────────────────────┬──────────┬──────────────────────────────────────────┐
 │  ░░ RULE                          │ SETTING  │  ░░ WHY                                   │
 ├────────────────────────────────────┼──────────┼──────────────────────────────────────────┤
 │  Require PR before merging        │  ✅ ON   │  No direct pushes to main                 │
 │  Required approving reviews       │  1 min   │  Maintainer review before merge            │
 │  Dismiss stale PR approvals       │  ✅ ON   │  Re-review after new commits               │
 │  Require code owner review        │  ✅ ON   │  Route reviews to the right people         │
 │  Require status checks to pass    │  ✅ ON   │  Tests must pass before merge              │
 │  Require branches up to date      │  ✅ ON   │  PRs must be rebased on latest main        │
 │  Restrict who can push            │  ✅ ON   │  Only maintainers can push directly        │
 │  Include administrators           │  ✅ ON   │  Rules apply to everyone, no exceptions    │
 │  Allow force pushes               │  ❌ OFF  │  Protect commit history                    │
 │  Allow deletions                  │  ❌ OFF  │  Prevent accidental branch deletion        │
 └────────────────────────────────────┴──────────┴──────────────────────────────────────────┘
```

---

## 3️⃣ CODEOWNERS

```
┌─────────────────────────────────────────────────────────────┐
│  ░░ .github/CODEOWNERS ░░  ·  Auto-assign reviewers        │
└─────────────────────────────────────────────────────────────┘
```

Create a `.github/CODEOWNERS` file:

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

## 4️⃣ Collaborator & Contributor Access

```
┌─────────────────────────────────────────────────────────────┐
│  ░░ SETTINGS → COLLABORATORS AND TEAMS ░░                   │
└─────────────────────────────────────────────────────────────┘
```

### ► Roles

```
 ┌─────────────┬───────────────────────────────────┬───────────────────────────────┐
 │  ░░ ROLE    │  ░░ ACCESS LEVEL                  │  ░░ WHO GETS THIS             │
 ├─────────────┼───────────────────────────────────┼───────────────────────────────┤
 │  Read       │  View code, open issues            │  General public (auto)        │
 │  Triage     │  Manage issues and PRs, no push    │  Community moderators         │
 │  Write      │  Push to non-protected branches    │  Trusted contributors         │
 │  Maintain   │  Manage repo (no destructive ops)  │  Core team members            │
 │  Admin      │  Full control                      │  Repository owners only       │
 └─────────────┴───────────────────────────────────┴───────────────────────────────┘
```

### ► Strategy for Controlled Open Source

1. ❌ **Do not** grant Write access broadly. Contributors fork the repo and open PRs.
2. ✅ Invite proven contributors as **Write** collaborators only after consistent quality contributions.
3. 🔒 Keep **Admin** access to 1–2 owners maximum.
4. 👥 Use **teams** (in an organization) to manage groups efficiently.

---

## 5️⃣ Fork Workflow

```
┌─────────────────────────────────────────────────────────────┐
│  ░░ HOW EXTERNAL CONTRIBUTORS WORK ░░                       │
└─────────────────────────────────────────────────────────────┘
```

Since the repo is public, anyone can:

1. 🍴 **Fork** the repository to their account
2. 🌿 Create a branch and make changes
3. 📬 Open a **Pull Request** back to your `main` branch
4. ⏳ Wait for your review and CI checks

You (maintainers) control:
- Whether the PR gets reviewed
- Whether it passes required checks
- Whether it gets merged

> 🔒 **No one outside your collaborator list can push directly to your repo.**

---

## 6️⃣ Actions & CI

```
┌─────────────────────────────────────────────────────────────┐
│  ░░ SETTINGS → ACTIONS → GENERAL ░░                         │
└─────────────────────────────────────────────────────────────┘
```

```
 ┌──────────────────────────────────────┬────────────────────────────────────────────────────┐
 │  ░░ SETTING                         │  ░░ VALUE                                           │
 ├──────────────────────────────────────┼────────────────────────────────────────────────────┤
 │  Actions permissions                │  Allow select actions and reusable workflows        │
 │  Fork PR workflows (first-time)     │  Require approval for first-time contributors      │
 │  Fork PR workflows (outside collab) │  Require approval for all outside collaborators     │
 └──────────────────────────────────────┴────────────────────────────────────────────────────┘
```

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

## 7️⃣ Security Settings

```
┌─────────────────────────────────────────────────────────────┐
│  ░░ SETTINGS → CODE SECURITY AND ANALYSIS ░░                │
└─────────────────────────────────────────────────────────────┘
```

```
 ┌──────────────────────────────────┬──────────┐
 │  ░░ FEATURE                     │ SETTING  │
 ├──────────────────────────────────┼──────────┤
 │  Dependency graph                │  ✅ ON   │
 │  Dependabot alerts               │  ✅ ON   │
 │  Dependabot security updates     │  ✅ ON   │
 │  Secret scanning                 │  ✅ ON   │
 │  Secret scanning push protection │  ✅ ON   │
 └──────────────────────────────────┴──────────┘
```

---

## 8️⃣ Issue & PR Templates

```
┌─────────────────────────────────────────────────────────────┐
│  ░░ TEMPLATE FILES ░░  ·  Standardize contributions         │
└─────────────────────────────────────────────────────────────┘
```

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

## 9️⃣ Tags & Releases

Use [Semantic Versioning](https://semver.org/):

```bash
git tag -a v0.2.0 -m "Release v0.2.0"
git push origin v0.2.0
```

Create a GitHub Release from the tag with a changelog summarizing what changed.

---

## ✅ Summary Checklist

```
 ╔═══════════════════════════════════════════════════════════╗
 ║  ░░ FINAL BOSS CHECKLIST ░░                               ║
 ╠═══════════════════════════════════════════════════════════╣
 ║                                                           ║
 ║  [ ] Repository set to Public                             ║
 ║  [ ] Branch protection on main with required reviews      ║
 ║  [ ] CODEOWNERS file created                              ║
 ║  [ ] Collaborator roles assigned (Admin = owners only)    ║
 ║  [ ] GitHub Actions CI workflow added                     ║
 ║  [ ] Security features enabled (Dependabot, scanning)     ║
 ║  [ ] Issue and PR templates created                       ║
 ║  [ ] LICENSE (Apache 2.0) exists                          ║
 ║  [ ] CONTRIBUTING.md exists                               ║
 ║  [ ] README.md has contributing and license sections      ║
 ║                                                           ║
 ╚═══════════════════════════════════════════════════════════╝
```

---

<p align="center">⬛⬜⬛ <a href="https://www.naaico.com"><strong>NAAICO</strong></a> ⬛⬜⬛</p>
