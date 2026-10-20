# 0015 — A walking skeleton, milestones, flat tasks

Date: 2026-10-19. Status: accepted.

## Context
The project was run from long step-by-step guides (31 hackathon steps, then 29 refactor steps) and several overlapping documents. Its owner felt they didn't own the codebase, and the plans had started to go stale.

## Decision
- **One document per kind:** `docs/architecture.md` (what), `docs/milestones.md` (order and acceptance), `docs/progress.md` (where things stand, plus a re-entry note) and `docs/decisions/` (why).
- **M1 is a walking skeleton:** the thinnest end-to-end path through the new CLI, with every part crude.
- **Milestones are usable states.** Each one answers "what can someone do now?". There are two releases: v0.2 after M8, and v0.3 after M10.
- **Tasks are flat.** Milestone → task, with one task per issue, each one or two sittings.
- **Work in progress is limited** to one active task, two at most, on a Now / Next / Later board.
- **Decisions are written down; plans are not.** Every session ends with a two-line re-entry note.

## Consequences
- The hackathon build guide and the v2 refactor guide stay in git history only (commit `3274e8b`).
- The R-step and Step numbers are retired. Tasks are named `M<n>-<nn>`.
