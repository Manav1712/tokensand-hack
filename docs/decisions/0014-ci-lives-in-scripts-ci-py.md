# 0014 — CI lives in `scripts/ci.py`, with a gate on every layer

Date: 2026-10-19. Status: accepted.

## Context
The hackathon suite had 169 example tests and no CI. The bugs that mattered were found by hand. The repository's remote is not GitHub today.

## Decision
- **CI logic lives in `scripts/ci.py`**, with the subcommands `lint`, `types`, `imports`, `test`, `coverage`, `mutate`, `docker`, `pr` and `nightly`. The workflow files only call it, so a contributor runs exactly what CI runs, and nothing depends on the host.
- **Layers L0–L8** (§16) each have a gate:
  - branch coverage ≥ 90% overall, and 100% on the fail-closed core;
  - mutation kill rate 100% on `policy.py`, ≥ 90% on the rest of the core;
  - Hypothesis properties;
  - metamorphic variants with no BLOCK flipping;
  - a benign-corpus ratchet;
  - an adversarial suite;
  - Docker under runc and runsc;
  - a nightly live-model run under a budget.

## Consequences
- The gates are built in M1 and M2, before most of the v2 modules exist. Each later module joins the gates in the task that creates it.
- Moving to GitHub needs only the workflow files.
