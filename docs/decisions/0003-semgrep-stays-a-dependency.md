# 0003 — Semgrep stays a required dependency

Date: 2026-10-14. Status: accepted.

## Context
The hackathon's only rule was a generic regex, which Python's `re` could run. Semgrep 1.180 is a heavy install and pins about 25 packages tightly.

## Decision
Keep Semgrep as a declared dependency. The reasons:
- its rule format can be reviewed;
- users can add their own rule packs;
- it can match Python and shell scripts by language (§9.4, M3-08).

Recommend `pipx` or `uv tool`, so its pins stay out of user environments. Fail closed on every Semgrep failure, with a liveness canary rule and a check that every target was scanned.

## Alternatives
Python `re` rules only. Rejected for now, because it gives up language-aware matching on `scripts/`. Revisit if M3-08 doesn't pay off.

## Consequences
- The supported Semgrep range is pinned and tested at both ends, in L3.
- `pip install` into an existing project venv may conflict, and the README says so.
