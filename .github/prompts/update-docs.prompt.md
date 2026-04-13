---
mode: agent
description: >
  Update README.md, requirements.md, and implementation-plan.md to reflect recent
  changes that were not yet documented. Use after a session where docs were skipped.
---

# Retrospective documentation update

Read the three documentation files and compare them to the current codebase, then bring them
fully up to date.

## 1. Audit the gap

- Read `README.md`, `requirements.md`, `implementation-plan.md`.
- Run `git log --oneline -20` to see recent commits.
- Read any changed source files needed to understand what was added.

## 2. Update README.md

Work through every section that may have changed:

- **Features** subsections (Scan / Review / Move / Infrastructure)
- **How it works** narrative
- **Project structure** file tree
- **Using the application** step-by-step guide
- **REST API table** — add any new or changed endpoints

## 3. Update requirements.md

- Add new FRs for any features that have no corresponding requirement.
- Update FRs whose wording no longer matches the implementation.
- Mark new requirements with a `†` footnote.
- Re-number any FRs that shifted.

## 4. Update implementation-plan.md

- Update each affected Phase to match what was actually built.
- Update **Key Decisions** with any non-obvious choices made.
- Remove references to things that were planned but superseded.

## 5. Commit

```powershell
git add README.md requirements.md implementation-plan.md
git commit -m "docs: retrospective documentation update"
git push origin main
```
