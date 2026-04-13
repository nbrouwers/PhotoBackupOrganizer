---
mode: agent
description: >
  Add a new feature end-to-end: implement the code, run tests, update all docs,
  commit and push. Use this prompt to ensure no step is missed.
---

# New Feature: ${input:featureDescription}

Follow the mandatory workflow from the workspace instructions. Complete every step in order.

## 1. Understand the scope

- Read every file you need to change before touching it.
- Identify the affected layers: backend (Python), API router, frontend (JS/HTML), tests.

## 2. Implement the feature

Apply the coding conventions from the workspace instructions:

- Python: type annotations, `from __future__ import annotations`, path-traversal protection.
- Router: Pydantic request model, correct HTTP status codes.
- JS: `data-*` attributes instead of inline JSON, `escHtml()` for output, `CSS.escape()` for selectors.
- Security: validate all user-supplied paths against the library root before use.

## 3. Add or update tests

- Add unit tests in `tests/` covering the new logic.
- Run the full suite — all tests must pass:
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/ -q
  ```

## 4. Update documentation (ALL FOUR files)

### README.md
- Features section: add a bullet in the relevant subsection (Scan / Review / Move / Infrastructure).
- How it works: update if the overall flow changed.
- Using the application: update the step-by-step guide if UX changed.
- REST API table: add any new endpoints.

### docs/requirements.md
- Add a new FR or update the existing one that this feature satisfies.
- Mark new requirements with a `†` footnote: `*† New requirement added during implementation.*`
- Re-number any FR references that shifted.

### docs/implementation-plan.md
- Update the affected Phase(s) with what was actually built.
- Add a Key Decision entry if a non-obvious design choice was made.

### docs/architecture.md
- Update any section whose description or diagram is affected by the feature:
  - New module or router → add it to the component tables and interaction diagram.
  - New data stored → update the Persistence section.
  - New design decision → add a row to the Key design decisions table.

## 5. Commit and push

Stage exactly the files changed (no unrelated files):

```powershell
git add <file1> <file2> ...
git commit -m "feat: ${input:featureDescription}"
git push origin main
```

Verify the push succeeded.