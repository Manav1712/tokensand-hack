# 0008 — The agent phase runs on a local or hosted model

Date: 2026-10-19. Status: accepted.

## Context
Many malicious skills ship no harmful script. Their `SKILL.md` instructs the agent instead. An earlier draft allowed only a loopback model, because tool output carries canary values. It also made every `--detonate` BLOCK when no local model was set up. The target user is an individual developer who brings their own API key.

## Decision
- The agent phase is opt-in with `--detonate=agent`. Plain `--detonate` never needs a model.
- The model can be local, or hosted with the user's own key. A hosted model receives only the jail transcript: the skill's own files and the per-run fake home. Nothing comes from the user's real machine.
- At most 24 calls per skill, all counted in the preflight.

## Consequences
- A hosted model may refuse to follow a malicious skill. That produces no evidence, which is accepted: a real hosted agent would face the same choice. The coverage line names the model so the user can weigh the result.
- The phase is strongest with local or self-tuned models.
