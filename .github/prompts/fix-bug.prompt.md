---
mode: agent
description: >
  Fix a bug: diagnose, implement the minimal fix, run tests, update docs if behaviour
  changed, commit and push. Use this prompt to ensure every step is covered.
---

# Bug fix: ${input:bugDescription}

Follow the mandatory workflow from the workspace instructions.

## 1. Diagnose

- Read the failing/affected files before touching anything.
- Identify the root cause — do not guess; trace the code path.
- Write a one-line summary of the root cause before starting the fix.

## 2. Implement the minimal fix

- Change only what is necessary. Do not refactor or clean up surrounding code.
- If the fix is security-relevant (path traversal, XSS, injection), note it in the commit message.

## 3. Run the full test suite

```powershell
.venv\Scripts\python.exe -m pytest tests/ -q
```

All tests must pass. If a test was wrong rather than the code, fix the test too and explain why.

## 4. Update documentation — only if observable behaviour changed

If the fix changes what the user sees or how an API behaves:
- `README.md` — update the relevant prose or REST API table entry.
- `docs/requirements.md` — update or add the FR that this fix satisfies.
- `docs/implementation-plan.md` — note the fix in the affected Phase if significant.
- `docs/architecture.md` — update if the fix changes a component, data flow, or design decision.

If the fix is purely internal (no behaviour change visible to users), documentation updates are
optional — skip them and say so in the commit message.

## 5. Commit and push

```powershell
git add <changed files>
git commit -m "fix: ${input:bugDescription}"
git push origin main
```
