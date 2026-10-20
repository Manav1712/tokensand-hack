# Skill Warden v2 progress

This is the handoff file for the v2 refactor. Read it before `docs/v2/refactor-guide.md`. Each session completes one step, updates this file, and stops.

The hackathon record is in `docs/progress.md`. Do not continue it.

## Next step

R1 — Declared dependencies and test markers

## Status

| Step | State | Acceptance |
| --- | --- | --- |
| R0 Baseline | done | `git log --oneline` shows `8a0f168 Initial commit`; 169 tests pass |
| R1 Dependencies and markers | not started | `DOCKER_HOST=unix:///nonexistent.sock python -m pytest -q` |
| R2 Domain types | not started | `python -m pytest tests/test_models.py -q` |
| R3 Policy | not started | `python -m pytest tests/test_policy.py -q` |
| R4 Intake | not started | `python -m pytest tests/test_intake.py tests/test_hashing.py -q` |
| R5 Static stage | not started | `python -m pytest tests/test_static_semgrep.py tests/test_rules.py -q` |
| R6 History | not started | `python -m pytest tests/test_history.py -q` |
| R7 Pipeline | not started | `python -m pytest tests/test_pipeline_static.py tests/test_pipeline_reader.py tests/test_pipeline_guards.py -q` |
| R8 Remove ClickHouse | not started | `python -m pytest -q` plus the grep check |
| R9 Reader core | not started | `python -m pytest tests/test_llm_reader.py -q` |
| R10 OpenAI-compatible adapter | not started | `python -m pytest tests/test_llm_openai_compat.py tests/test_llm_reader.py -q` |
| R11 Anthropic adapter | not started | `python -m pytest tests/test_llm_anthropic.py -q` |
| R12 Config and paths | not started | `python -m pytest tests/test_config.py -q` |
| R13 `scan` | not started | `python -m pytest tests/test_cli_scan.py -q` |
| R14 `init`, `doctor`, `history`, `show` | not started | `python -m pytest tests/test_cli_other.py -q` |
| R15 Images and package data | not started | `python -m pytest tests/test_detonate_images.py tests/test_jail_plan.py tests/test_honeytoken.py tests/test_observe.py -q` |
| R16 Per-run sink | not started | `python -m pytest tests/test_sink_unit.py -q && python -m pytest -m docker tests/test_sink.py -q` |
| R17 Detonation stage | not started | `python -m pytest tests/test_detonation_stage.py -q && python -m pytest -m docker tests/test_detonate.py -q` |
| R18 Isolation check | not started | `python -m pytest tests/test_isolation.py tests/test_detonation_stage.py tests/test_policy.py -q && python -m pytest -m docker tests/test_isolation_docker.py tests/test_detonate.py -q` |
| R19 Lived-in home and canary registry | not started | `python -m pytest tests/test_honeytoken.py tests/test_jail_plan.py tests/test_detonation_stage.py -q && python -m pytest -m docker tests/test_detonate.py -q` |
| R20 Canary matching and written files | not started | `python -m pytest tests/test_canary.py tests/test_observe.py tests/test_findings.py tests/test_history.py tests/test_cli_scan.py -q && python -m pytest -m docker tests/test_detonate.py -q` |
| R21 Responsive sink | not started | `python -m pytest tests/test_exfil_hosts.py tests/test_findings.py tests/test_sink_unit.py -q && python -m pytest -m docker tests/test_sink.py tests/test_detonate.py -q` |
| R22 Phases and coverage | not started | `python -m pytest tests/test_phases.py tests/test_policy.py -q && python -m pytest -m docker tests/test_detonate.py -q` |
| R23 Agent phase | not started | `python -m pytest tests/test_mini_agent.py tests/test_phases.py tests/test_config.py -q && python -m pytest -m docker tests/test_detonate.py -q` |
| R24 Profiles and clock skew | not started | `python -m pytest tests/test_profiles.py tests/test_findings.py tests/test_policy.py -q && python -m pytest -m docker tests/test_detonate.py -q` |
| R25 Eval matrix and guarantees | not started | `python -m pytest tests/test_canary_leak.py -q && python -m pytest -m docker tests/test_eval_matrix.py tests/test_isolation_regression.py tests/test_determinism.py -q`, then `python scripts/eval_detonation.py --corpus fixtures/eval --out .eval` |
| R26 Ruleset and golden table | not started | `python -m pytest tests/test_golden.py tests/test_rules.py -q` |
| R27 Packaging | not started | `python -m pytest -m packaging -q` |
| R28 Docs and full regression | not started | default, `docker` and `packaging` suites and the eval script all exit 0 |
| G1 Local LLM | not started | needs `ollama serve` and a pulled model |
| G2 Hosted LLM | not started | needs `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` |
| G3 Detonation on a clean machine | not started | needs Docker |
| G4 Linux install | not started | needs a Linux machine or VM |
| G5 runc floor | not started | needs Docker Desktop updated until runc ≥ 1.2.8 (1.2.x) or ≥ 1.3.3 (1.3.x); R18–R25 docker acceptance depends on it |

State is one of `not started`, `done`, `blocked` or `failed`.

## Limitations

Carry these forward until a later log entry retires them.

- Baseline on 14 October 2026: 169 tests pass with Docker 28.5.1 running, Semgrep 1.180.0 on `PATH` (from `.venv/bin`) and Python 3.14.7. The container `skill-warden-ch-test` is still running on port 18123. The ClickHouse-backed tests need it until R8.
- The code has not changed yet. `docs/v2/architecture.md` §17.1 lists 16 defects in the current code that the steps fix, including fail-open Semgrep handling, which was verified.
- On 16 October 2026 this Mac reported Docker Engine 28.5.1 with runc 1.2.5. That is below the R18 floor, so R18's docker acceptance, and every later Phase 4 docker command, fails here until G5. Don't lower the floor. R26 and R27 may run while R18 is blocked.
- From R23 on, `--detonate` needs a local loopback agent model. Without one, every detonation is BLOCK `tool_error` (`coverage_incomplete`). This is intended.
- `demo/` is out of scope. `scripts/export_demo_traces.py` stops working at R8, but the deck still builds from the committed `traces.json`.

## Guide updates

| Date | Steps changed | Why |
| --- | --- | --- |
| 2026-10-16 | R15, R16 and R17 extended. New R18–R25. Old R18–R20 renumbered to R26–R28. Map tables, R26 golden note, R27 package data, R28 docs and acceptance, human gates (G3 revised, G5 added) and Definition of done updated. `docs/v2/architecture.md` §11.1, §11.4–§11.7, §12 new cases, §16.2, §17.2, §18, §19 item 5 and §20 updated | Ports the detonation hardening from `docs/build-guide.md` Steps 19–26 and its deferred list into v2. Kept as new steps rather than folded into R15–R17: each is one session's work, and splitting lets R17 be verified on this Mac before the R18 runc floor blocks the docker tests. R15 takes every image change up front, so the content-addressed tags change once. v2 has no `policy` source, so `isolation_failed` and `coverage_incomplete` are `jail` / error findings, which §12 row 6 already turns into BLOCK `tool_error`. `policy.py` is unchanged. Docker tests use `full=True` so a static hit can't skip the jail. The eval uses a detonation-only decision so R26's rules can't move it |

## Log

### 2026-10-14 — R0 Baseline

- Result: done. The operator made the baseline commit.
- Acceptance: `git log --oneline` shows `8a0f168 Initial commit`, and `git status` shows only `docs/v2/` as new. `PATH=.venv/bin:$PATH python -m pytest tests -q` reported 169 passed on the same, unchanged code earlier the same day.
- Secret scan: `git grep` for real-format AWS, GitHub, Anthropic and AkashML keys and for private-key blocks found none. The only hits are the prefixes in docs, the nonce-built values in `honeytoken.py`, and the truncated previews (`AKIA…`) in `demo/src/data/traces.json`.
- Files: none (baseline only)
- Limitations: the remote is `origin` on Cursor. `docs/v2/` is not committed yet.
- Deviation: none

### 2026-10-14 — plan only

No code changed. `docs/v2/architecture.md` and `docs/v2/refactor-guide.md` are the plan. The next session starts at R0.

## Template for the next entry

When a step finishes, copy this to the top of `## Log`. Update `Next step`, the status table and Limitations in the same edit.

```markdown
### YYYY-MM-DD — Rn title

- Result: done | blocked | failed
- Acceptance: `<command>` exited 0 | non-zero
- Files: list
- Limitations: what the next session must not assume. Empty if none.
- Deviation: none, or one paragraph. If this changes a later step, list the guide sections you edited.
```
