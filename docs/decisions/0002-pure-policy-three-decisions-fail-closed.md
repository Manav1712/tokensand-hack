# 0002 — A pure policy with three decisions, failing closed

Date: 2026-10-14, revised 2026-10-19. Status: accepted.

## Context
The research suggested a fourth outcome, INCONCLUSIVE, for runs that observed nothing. The design also has to tell "Warden couldn't check" from "the skill was slow" (§11.8).

## Decision
- `policy.decide` is the only decider. It is pure, first-match, and returns BLOCK, ASK or ALLOW.
- Anything requested that didn't run or didn't finish is BLOCK, with the stage named. That covers a missing stage result, a parse failure, a tool error, an isolation failure and a command that couldn't start.
- `error` findings mean "Warden couldn't check". The user fixes their setup or the skill. An approval can't cover them.
- A command that ran but was cut off by its time limit is a medium finding (ASK), unless it was stalling.

## Alternatives
A fourth INCONCLUSIVE decision. Rejected: every consumer (the CLI exit codes, JSON, CI) would need a new branch, and "not checked" already has an honest answer, which is BLOCK with a reason.

## Consequences
Evidence only accumulates, so a stage can't lower another stage's finding. That is what makes the short-circuit safe. ALLOW never means "safe". It means no stage that ran found evidence, and the report lists the stages.
