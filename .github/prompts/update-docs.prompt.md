---
mode: agent
description: >
  Update README.md, docs/requirements.md, docs/implementation-plan.md, and
  docs/architecture.md to reflect recent changes that were not yet documented.
  Use after a session where docs were skipped.
---

# Retrospective documentation update

Read the four documentation files and compare them to the current codebase, then bring them
fully up to date.

## 1. Audit the gap

- Read `README.md`, `docs/requirements.md`, `docs/implementation-plan.md`, `docs/architecture.md`.
- Run `git log --oneline -20` to see recent commits.
- Read any changed source files needed to understand what was added.

## 2. Update README.md

Work through every section that may have changed:

- **Features** subsections (Scan / Review / Move / Infrastructure)
- **How it works** narrative
- **Project structure** file tree
- **Using the application** step-by-step guide
- **REST API table** — add any new or changed endpoints

## 3. Update docs/requirements.md

- Add new FRs for any features that have no corresponding requirement.
- Update FRs whose wording no longer matches the implementation.
- Mark new requirements with a `†` footnote.
- Re-number any FRs that shifted.

## 4. Update docs/implementation-plan.md

- Update each affected Phase to match what was actually built.
- Update **Key Decisions** with any non-obvious choices made.
- Remove references to things that were planned but superseded.

## 5. Update docs/architecture.md

- Update component tables, diagrams, and data-flow sections to reflect any new or changed
  modules, endpoints, or design decisions.
- Add new rows to the Key design decisions table when a non-obvious choice was made.

## 6. Commit

```powershell
git add README.md docs/requirements.md docs/implementation-plan.md docs/architecture.md
git commit -m "docs: retrospective documentation update"
git push origin main
```
