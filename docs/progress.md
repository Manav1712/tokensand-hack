# Skill Warden progress

Read this first when you come back. The plan is `docs/milestones.md`, the design is `docs/architecture.md`, and the reasons are in `docs/decisions/`.

## Re-entry note

Newest first. Two lines per session: where you stopped, and what's next. **Stopped** is the last thing that session finished. The task in that line landed. The open task is **Now** on the board.

- **2026-10-27:**
  - **Stopped:** M1-09 and M1-10. `skill-warden scan` takes one or more skill directories, optional `--llm PROVIDER:MODEL` with `--llm-base-url` and `--llm-key-env`, `--detonate`, `--format text|json`, and `--no-history`. Several paths exit with the worst verdict. JSON uses the `skill-warden/scan@1` envelope. A key in the environment is redacted from the output. Bad input exits 2 and scans nothing. `pytest -m packaging` builds a wheel, installs it into a fresh venv, and scans a copied fixture from outside the repository.
  - **Next:** M2-01 Coverage and Hypothesis. M1 acceptance is still open for `pipx install` and for `scan --detonate` from the CLI.
- **2026-10-25:**
  - **Stopped:** M1-08. Each scan appends one row to `<data dir>/history.sqlite3` with the skill path, content hash, decision, reason, and report. `history=False` writes nothing. A failed write prints a warning and leaves the report unchanged.
  - **Next:** M1-09 `skill-warden scan`.
- **2026-10-24:**
  - **Stopped:** M1-06 and M1-07. `scan_skill` hashes a folder, runs Semgrep, maps findings, and asks the policy. A thrown stage is BLOCK `not_finished`, and `scan` continues with the next skill. `MemoryStore` is the jail's store, so detonation does not need ClickHouse.
  - **Next:** M1-08 Crude history.
- **2026-10-24:**
  - **Stopped:** M1-05. The memory rule ships in the package. `rule_path()` loads it with `importlib.resources`, and a scan from an installed wheel finds `skill-memory-file-persistence`.
  - **Next:** M1-06 Crude pipeline.
- **2026-10-22:**
  - **Stopped:** M1-04. `policy.decide` picks BLOCK, ASK, or ALLOW from findings, requested stages, and how the run ended. The 19 ClickHouse cases plus the reader and detonation gaps pass with no database.
  - **Next:** M1-05 Package the rules.
- **2026-10-22:**
  - **Stopped:** M1-03 added frozen Finding, Verdict, and Report. A scanner row converts to a Finding and back, including source `policy` and the evidence hash.
  - **Next:** M1-04 Crude policy.
- **2026-10-21:**
  - **Stopped:** Fixed the PR CI failure. GitHub failed because `skill-warden-observe:step16` was never built on a clean runner. Also fixed x86_64 Alpine using `open` instead of `openat`: the parser and jail strace filter now cover both. `.venv/bin/python scripts/ci.py pr` exits 0 locally (120 + 56).
  - **Next:** M1-03 Minimal domain types.
- **2026-10-20:**
  - **Stopped:** M1-01 and M1-02 landed. `scripts/ci.py pr` failed one x86_64 strace test; see the 2026-10-21 note for the fix.
  - **Next:** Fix the CI observe-image / openat failure.
- **2026-10-19:**
  - **Stopped:** docs consolidated into one architecture, one milestone plan, one progress file and 15 decision records. No code changed.
  - **Next:** M1-01, declared dependencies and test markers. Run `PATH=.venv/bin:$PATH python -m pytest tests -q` first to confirm the baseline still passes 169.

## Board

Limit: one task in **Now**, two at most.

- **Now:** M2-01 Coverage and Hypothesis.
- **Next:** M2-02 Mutation testing and fault injection.
- **Later:** the rest of M2, then M3–M10 in order.

## Milestones

| Milestone | State | Notes |
| --- | --- | --- |
| M0 Hackathon baseline | done | 169 tests passed on 14 October 2026. Commits `8a0f168` (code) and `3274e8b` (plans) |
| M1 Walking skeleton | in progress | M1-01 through M1-10 done. Acceptance still open for `pipx install` and `scan --detonate` from the CLI. `scripts/ci.py pr` exits 0 |
| M2 Fail-closed core | not started | |
| M3 Detection quality | not started | |
| M4 Bring your own model | not started | |
| M5 Living with false positives | not started | |
| M6 Safe detonation | not started | Docker acceptance needs G5 on this Mac |
| M7 Detonation that catches theft | not started | |
| M8 v0.2.0 release | not started | License still to choose (M8-05) |
| M9 Agent phase | not started | |
| M10 Evasion-resistant detonation (v0.3.0) | not started | |

State is one of `not started`, `in progress`, `done` or `blocked`. A milestone is done when every acceptance box in `docs/milestones.md` is ticked.

## Operator gates

| Gate | State | Needs |
| --- | --- | --- |
| G1 Local model | not started | `ollama serve` and a pulled model |
| G2 Hosted model | not started | `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` |
| G3 Detonation on a clean machine | not started | Docker at or above the runc floor, with network for the first image build |
| G4 Linux install | not started | A Linux machine or VM |
| G5 runc floor | blocked | This Mac reported Docker Engine 28.5.1 with runc 1.2.5 on 16 October 2026. Update Docker Desktop until runc is ≥ 1.2.8 (1.2.x) or ≥ 1.3.3 (1.3.x) |
| G6 Agent model | not started | A local model or a hosted key for `--detonate=agent` (M9) |

## What the code is today

Commit `ae13381`. M1-01 through M1-07 are in the tree. There is no `skill-warden` command and no history file yet (M1-08, M1-09).

- **Walking skeleton:**
  - `pipeline.scan_skill` hashes the folder (`hashing.content_hash`, still v1), runs Semgrep, maps rows to frozen `Finding`s (`models.py`), and asks `policy.decide`;
  - the memory rule is `src/skill_warden/rules/memory.yaml`, loaded by `semgrep.rule_path()` through `importlib.resources`;
  - an optional reader is `reader.Reader`. An optional detonation calls `jail.detonate` with a `MemoryStore`, and `MemoryStore.verdict` calls `policy.decide`. That path does not use ClickHouse;
  - a thrown stage returns BLOCK `not_finished`, and `scan` continues with the next skill.
- **Hackathon path, still present until M2:**
  - `orchestrator.py` runs host Semgrep (`semgrep.py`) and the reader (`reader.py`, AkashML defaults), then maps everything through `findings.build_rows`;
  - rows are inserted into ClickHouse (`store.py`), and `schema/verdict.sql` picks the verdict.
- **Jail:**
  - `jail.detonate` packs the skill and plants a honeytoken home (`honeytoken.py`);
  - it starts a DNS and HTTP sink on the fixed network `jailnet` (`sink.py`) and runs `scripts/*.sh` and `SKILL.md` blocks under strace in a hardened Alpine container;
  - it parses the trace and the diff (`observe.py`), and writes to the store it was given (`MemoryStore` or ClickHouse).
- **Also present:** `registry.py`, `redact.py`, `breaker.py` and `memory.py` (hackathon-only), plus `demo/` (out of scope). No `cli.py` and no `history.py`.
- **Tests:** On 25 October 2026 the default suite passed 173 and deselected 58 (57 `docker`, 1 `packaging`). `python scripts/ci.py pr` is lint, that default suite, then `pytest -m docker`.
- **Known defects:** the 21 rows of architecture §17.1. M1 did not close them, except that the Semgrep rule path in row 10 now uses `importlib.resources`. Docker contexts and `verdict.sql` still use the old lookup. Each remaining row is fixed by a later milestone task.

## Things to know before you start

- Semgrep 1.180.0 lives in `.venv/bin`. Put it on `PATH` (`PATH=.venv/bin:$PATH`) until M2-11 resolves it next to `sys.executable`.
- The ClickHouse test container `skill-warden-ch-test` runs on port 18123, with admin and `scanner` passwords `test`. The old tests need it until M2-14 removes ClickHouse.
- The baseline ran on Python 3.14.7 with Docker 28.5.1. The design targets Python ≥ 3.11.
- The git remote is `origin` on GitHub (`Manav1712/tokensand-hack`). CI logic stays in `scripts/ci.py` (decision 0014). `.github/workflows/pr.yml` only calls `python scripts/ci.py pr`.
- Never commit a real key. Fixtures use `example.invalid`, `EXAMPLE_TOKEN` and `FAKE-CANARY`.

## History

| Date | What happened |
| --- | --- |
| 2026-10-09 | Hackathon build: Steps 0–18 done in one day (package through orchestrator guards, including the first live detonation). |
| 2026-10-14 | v2 designed as a downloadable CLI (decision 0001). Baseline commit `8a0f168`. |
| 2026-10-16 | Detonation research folded into the plan: isolation check, lived-in home, value-flow canaries, answering sink, phases, agent turn, profiles, evaluation. |
| 2026-10-19 | Architecture audit. Operator decisions: two releases, manual approvals, a local or hosted agent model, per-command time limits with slow meaning ASK, medium probe severities, a Debian jail, hash v2, frontmatter read twice, a root-only trace channel, bounded capture, and layered test gates (decisions 0002 and 0005–0014). |
| 2026-10-19 | Docs consolidated. The work is organized as a walking skeleton plus milestones (decision 0015). The old guides are retired and live in git history at `3274e8b`. |
| 2026-10-20 | M1-01 and M1-02. Dependencies and markers are declared. `scripts/ci.py` runs lint, the default tests, and the Docker tests. `.github/workflows/pr.yml` calls `pr`. |
| 2026-10-21 | The PR check builds the observe image on a clean runner. The strace parser covers Alpine `open` and `openat`. |
| 2026-10-22 | M1-03. Frozen Finding, Verdict, and Report in `models.py`. |
| 2026-10-22 | M1-04. `policy.decide` ports the verdict SQL. The 19 cases pass with no ClickHouse. |
| 2026-10-24 | M1-05. The memory rule ships in the package and loads through `importlib.resources`. |
| 2026-10-24 | M1-06 and M1-07. `pipeline.scan_skill` and `MemoryStore`. A thrown stage is BLOCK `not_finished`. Detonation does not need ClickHouse. |
