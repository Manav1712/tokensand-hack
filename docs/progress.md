# Skill Warden progress

Read this first when you come back. The plan is `docs/milestones.md`, the design is `docs/architecture.md`, and the reasons are in `docs/decisions/`.

## Re-entry note

Newest first. Two lines per session: where you stopped, and what's next.

- **2026-11-05:**
  - **Stopped:** `content_hash_v2` fails closed. An unlistable directory or an unreadable file raises `SkillTreeError("unreadable")` with no path in the message. Path bytes go through `os.fsencode`, so a non-UTF-8 name is hashed. Owner-only execute (`0o744`) matches any other execute bit, and setuid without an execute bit stays `-`. A matching approval is still ignored. `StageResult.public()` is the safe mapping; `asdict` still includes secrets. `PATH=.venv/bin:$PATH .venv/bin/python scripts/ci.py pr` exits 0 (373 passed under coverage, 92.19% overall). `hashing.py` and `policy.py` are at 100% branch coverage. `policy.py` is 188/188 mutants killed. `hashing.py` is 113/120 (94.2%): the five equivalent v1 survivors remain, and two v2 survivors drop the explicit `"big"` byteorder, which is the default.
  - **Next:** M2-07 Intake inventory. M1 acceptance is still open for `pipx install` and `scan --detonate` from the CLI.
- **2026-11-05:**
  - **Stopped:** M2-06. `content_hash_v2` hashes every regular file, including `HASH` and dotfiles, with a mode byte (`x` if any execute bit is set, otherwise `-`) and length-prefixed path and bytes. v1 `content_hash` still skips `HASH`. The pipeline and registry still call v1. §16.3 hash properties pass. `hashing.py` is at 100% branch coverage and about 95% mutants killed; the five surviving v1 mutants are the same equivalent ones as on 2026-11-03. `PATH=.venv/bin:$PATH .venv/bin/python scripts/ci.py pr` exits 0 (366 passed under coverage).
  - **Next:** M2-07 Intake inventory. M1 acceptance is still open for `pipx install` and `scan --detonate` from the CLI.
- **2026-11-05:**
  - **Stopped:** M2-05. `decide(outcome, approval=None)` implements §12 rows 1–11 and 13. `approval` is accepted and unused; covered findings stay M5-01. The crude pipeline still requests only `static` and passes hash version 1. `policy.py` is on the core and mutation lists: 100% branch coverage and 188/188 mutants killed. `.venv/bin/python scripts/ci.py pr` exits 0 (352 passed under coverage).
  - **Next:** M2-06 Content hash v2. M1 acceptance is still open for `pipx install` and `scan --detonate` from the CLI.
- **2026-11-05:**
  - **Stopped:** M2-04. `models.py` has frozen `FileEntry`, `SkillRecord` (`hash_version`, optional `content_sha256`), `StageResult` (`secrets` omitted from `repr` and `public()`), `RunOutcome` (`content_sha256` and `hash_version`), and `Approval`. `Verdict.approval` defaults to `None`. The crude `Report` and `registry.SkillRecord` are unchanged. `.venv/bin/python scripts/ci.py pr` exits 0 (328 passed under coverage).
  - **Next:** M2-05 Policy: the full decision table. M1 acceptance is still open for `pipx install` and `scan --detonate` from the CLI.
- **2026-11-04:**
  - **Stopped:** Pull-request CI was red on #14 and #15 after the tests passed. `mutate --changed` asked for a local `main`, and the depth-1 checkout of `refs/pull/N/merge` has none. It now diffs against `origin/main` (local `main` if that remote ref is absent) and the workflow fetches full history so `origin/main` exists. The git error is included when the base is missing.
  - **Next:** M2-04 Full domain types. M1 acceptance is still open for `pipx install` and `scan --detonate` from the CLI.
- **2026-11-04:**
  - **Stopped:** M2-03. `mypy` and `import-linter` are dev dependencies. `scripts/ci.py types` runs `mypy --strict` on `[tool.mypy] files` (the v2 modules that exist). `scripts/ci.py imports` runs `lint-imports`: `skill_warden` does not import `tests` or `scripts`, and `semgrep`, `reader`, and `jail` do not import `cli`. An AST test allows `Verdict(...)` only in `policy.py`. A thrown stage calls `policy.block_not_finished()`; detonation asks `decide` with `MemoryStore.run_status`. `llm/` and `detonate/` are not packages yet, so that contract waits for M4-09. `pr` runs lint, types, imports, coverage, then `mutate --changed`. `.venv/bin/python scripts/ci.py pr` exits 0 (309 passed under coverage).
  - **Next:** M2-04 Full domain types. M1 acceptance is still open for `pipx install` and `scan --detonate` from the CLI.
- **2026-11-03:**
  - **Stopped:** M2-02. `mutmut>=3.8,<4` is a dev dependency. `scripts/ci.py mutate` runs mutmut per core file (100% floor for `policy.py`, ≥ 90% otherwise); `mutate --changed` scopes to the merge-base diff; `pr` runs lint, coverage, then `mutate --changed`. `fake_binary` puts an executable first on `PATH`. First `redact.py` survivors included the 4-character boundary, longest-first replace, rebuild delete order, and `find` vs `rfind`; new tests kill all but equivalent mutant `x_redact__mutmut_5` (`and False` on the marker check). `hashing.py` is above 90%; remaining survivors are equivalent (`sorted` without key, `UTF-8`, default `to_bytes` byteorder).
  - **Next:** M2-03 Strict types and import contracts. M1 acceptance is still open for `pipx install` and `scan --detonate` from the CLI.
- **2026-11-02:**
  - **Stopped:** M2-01. `coverage[toml]` and `hypothesis` are dev dependencies. `scripts/ci.py coverage` runs the unit and docker tests under branch coverage, requires 90% overall, and requires 100% on `[tool.skill_warden.core]` (`redact.py` and `hashing.py`). It fails when a core line or branch is uncovered. Hypothesis profiles are `dev` (100 examples), `ci` (500) and `nightly` (5000). `ci.py pr` runs ruff, then that gate. The §16.3 redaction property passes for raw secrets.
  - **Next:** M2-02 Mutation testing and fault injection. M1 acceptance is still open for `pipx install` and `scan --detonate` from the CLI.
- **2026-10-28:**
  - **Stopped:** The five copied ClickHouse test harnesses are one `scanner` fixture. The three copies of the skill-file walk are `hashing.skill_files`. The two secret checks are `redact.contains_secret`.
  - **Next:** M1 acceptance is still open for `pipx install` and `scan --detonate` from the CLI. Then M2-01.
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

- **Now:** M2-07 Intake inventory.
- **Next:** M2-08 Normalized copy.
- **Later:** M2-08 through M2-14, then M3–M10 in order. M1 acceptance (`pipx install`, and `scan --detonate` from the CLI) is still open.

## Milestones

| Milestone | State | Notes |
| --- | --- | --- |
| M0 Hackathon baseline | done | 169 tests passed on 14 October 2026. Commits `8a0f168` (code) and `3274e8b` (plans) |
| M1 Walking skeleton | in progress | M1-01 through M1-10 done. Acceptance still open for `pipx install` and `scan --detonate` from the CLI. `scripts/ci.py pr` exits 0 |
| M2 Fail-closed core | in progress | M2-01 through M2-06 done. M2-07 is next |
| M3 Detection quality | not started | |
| M4 Bring your own model | not started | |
| M5 Living with false positives | not started | |
| M6 Safe detonation | not started | Docker acceptance needs G5 on this Mac |
| M7 Detonation that catches theft | not started | |
| M8 v0.2.0 release | not started | License still to choose (M8-05) |
| M9 Agent phase | not started | |
| M10 Evasion-resistant detonation (v0.3.0) | not started | |

State is one of `not started`, `in progress`, `done` or `blocked`. A milestone is done when every acceptance box in `docs/milestones.md` is ticked.

## M2 tasks

Fail-closed core. Do these in order, one at a time. Tick a box when that task's "done when" in `docs/milestones.md` holds. Scope changes belong in that file.

- [x] **M2-01 — Coverage and Hypothesis.** Dev dependencies `coverage[toml]` and `hypothesis`. `scripts/ci.py coverage` enforces 90% overall and 100% on `[tool.skill_warden.core]`, starting with `redact.py` and `hashing.py`. Profiles `dev`, `ci` (500 examples) and `nightly` (5000). Done when the §16.3 redaction property passes for raw secrets, and the gate fails when a core line is uncovered.
- [x] **M2-02 — Mutation testing and fault injection.** `mutmut` and `scripts/ci.py mutate [--changed]`: 100% on `policy.py`, at least 90% on the rest of the core. The `fake_binary` fixture puts an executable at the front of `PATH`. Done when mutmut on `redact.py` lists its survivors, the new tests kill them, and `tests/test_fakes.py` passes.
- [x] **M2-03 — Strict types and import contracts.** `mypy --strict` on the v2 module list, and `import-linter` for the §16.1 contracts. An AST walk checks that only `policy.py` constructs `Verdict`. Done when `scripts/ci.py types` and `imports` run inside `pr`.
- [x] **M2-04 — Full domain types.** `FileEntry`, `SkillRecord` with `hash_version`, `StageResult` with non-serialized `secrets`, `RunOutcome` with `content_sha256` and `hash_version`, `Approval`, and `Verdict.approval`. Done when `tests/test_models.py` covers the new types.
- [x] **M2-05 — Policy: the full decision table.** `decide(outcome, approval=None)` for §12 rows 1–11 and 13. Rows 8–10 are a requested stage that came back without findings. Add `policy.py` to the core and mutation lists. Done when every §12 case with no approval passes, determinism and monotonicity hold, and the mutation floor is 100%.
- [x] **M2-06 — Content hash v2.** `hashing.content_hash_v2` covers every file, including `HASH` and dotfiles, with a mode byte for the execute bit and length-prefixed entries. Done when the §16.3 hash properties pass, including "a top-level `HASH` file changes the hash".
- [ ] **M2-07 — Intake inventory.** `intake.discover` and `load_skill`: symlink and FIFO errors, the caps, text and binary classification, and `intake.case_collisions`. Done when `tests/test_intake.py` covers §8 steps 1, 2 and 4. The end-to-end case-collision test is marked `case_sensitive_fs`.
- [ ] **M2-08 — Normalized copy.** NFKC plus `Cf` stripping into a private 0700 temporary directory, with `obfuscation.unicode` recorded against the file. Done when a U+200B inside `MEMORY.md` gives a finding and a clean copy, and a non-breaking space alone gives no finding.
- [ ] **M2-09 — Frontmatter read two ways.** `frontmatter.py` compares `yaml.safe_load` with the line parser, per §8 step 6. Add `pyyaml`. Done when `tests/test_frontmatter.py` has one test per table row, a `!!python/object` tag never builds an object, and the agreement property holds for generated frontmatter inside the subset.
- [ ] **M2-10 — Hostile trees.** 30 levels of nesting, a 255-byte name, an invalid-UTF-8 name, a symlink loop, a FIFO, a sparse file larger than the cap, and names that collide after NFKC. Done when each gives a named finding and none raises.
- [ ] **M2-11 — Static stage, fail-closed.** `static/semgrep.py` resolves the binary next to `sys.executable` first, passes explicit file targets, uses a minimal subprocess environment, covers every §9.3 row, and runs the liveness canary. Done when each §9.3 row has a test with an injected `run` and one with `fake_binary`.
- [ ] **M2-12 — Fix the memory rule.** The regex is a single-line scalar. Add the `dotslash-memory` and `zero-width-memory` fixtures. Done when `append the note to ./MEMORY.md` is BLOCK, and the reachability test emits `skill-memory-file-persistence` from a fixture.
- [ ] **M2-13 — Pipeline proper.** Replace the crude pipeline with the §7 stage protocol: stage isolation, short-circuit with `--full`, the `"auto"` global clock, and redaction before rendering. A secret in output is BLOCK `not_finished`. Done when `tests/test_pipeline_guards.py` covers §7.2 and §7.3, and no stage receives `os.environ`.
- [ ] **M2-14 — Remove ClickHouse and the dead modules.** Delete `store`, `verdict`, `breaker`, `memory`, `registry`, `orchestrator`, the old `semgrep.py`, `jail.detonate`, `MemoryStore`, `schema/*.sql`, `scripts/try_sample_skill.py`, their tests, and v1 `content_hash`. Port `test_first_block.py` and `test_reader_path.py` to the pipeline tests. Done when the acceptance grep is clean and the suite passes without `clickhouse-connect`. There is no end-to-end detonation from here until M6-04.

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

Two paths share the jail:

- **CLI (M1):** `skill-warden scan` calls `pipeline.scan`. That still hashes the folder with v1 `content_hash`, runs Semgrep, maps findings, and asks `policy.decide(RunOutcome)`. `content_hash_v2` exists and is not wired in until intake. `--llm` calls the reader. `--detonate` runs `jail.detonate` through `MemoryStore`, with no ClickHouse. A scan can append one row to `<data dir>/history.sqlite3`.
- **ClickHouse (until M2-14):** `orchestrator.py` still writes to `store.py`, and `schema/verdict.sql` still picks that verdict. `breaker.py`, `memory.py`, and `registry.py` stay on this path.
- **Jail:** `jail.detonate` packs the skill, plants a honeytoken home, and runs `scripts/*.sh` and `SKILL.md` blocks under strace. The sink is the fixed network `jailnet`.
- **Checks:** `python scripts/ci.py pr` runs ruff, then `ci.py types`, then `ci.py imports`, then `ci.py coverage`, then `ci.py mutate --changed`. `types` is `mypy --strict` on the v2 module list in `[tool.mypy] files`. `imports` is import-linter. Coverage runs the unit and docker tests under branch coverage and requires 90% overall and 100% on `redact.py`, `hashing.py`, and `policy.py`. `mutate --changed` diffs against `origin/main` when that ref exists, otherwise local `main`. The workflow fetches full history so a pull request has `origin/main`. Mutation kill rate is 100% on `policy.py` and at least 90% on the other core files. `ci.py test` and `ci.py docker` still run those suites on their own. The docker tests share one ClickHouse `scanner` fixture.
- **Known defects:** the 21 rows of architecture §17.1. Each is fixed by a milestone task.

## Things to know before you start

- Semgrep 1.180.0 lives in `.venv/bin`. Put it on `PATH` (`PATH=.venv/bin:$PATH`) until M2-11 resolves it next to `sys.executable`.
- The ClickHouse test container `skill-warden-ch-test` runs on port 18123, with admin and `scanner` passwords `test`. The old tests need it until M2-14 removes ClickHouse.
- The baseline ran on Python 3.14.7 with Docker 28.5.1. The design targets Python ≥ 3.11.
- The git remote is `origin` on Cursor, not GitHub. All CI logic goes in `scripts/ci.py` (decision 0014), so the gates run locally. The workflow files only matter once the repository is on GitHub.
- Never commit a real key. Fixtures use `example.invalid`, `EXAMPLE_TOKEN` and `FAKE-CANARY`.

## History

| Date | What happened |
| --- | --- |
| 2026-10-09 | Hackathon build: Steps 0–18 done in one day (package through orchestrator guards, including the first live detonation). |
| 2026-10-14 | v2 designed as a downloadable CLI (decision 0001). Baseline commit `8a0f168`. |
| 2026-10-16 | Detonation research folded into the plan: isolation check, lived-in home, value-flow canaries, answering sink, phases, agent turn, profiles, evaluation. |
| 2026-10-19 | Architecture audit. Operator decisions: two releases, manual approvals, a local or hosted agent model, per-command time limits with slow meaning ASK, medium probe severities, a Debian jail, hash v2, frontmatter read twice, a root-only trace channel, bounded capture, and layered test gates (decisions 0002 and 0005–0014). |
| 2026-10-19 | Docs consolidated. The work is organized as a walking skeleton plus milestones (decision 0015). The old guides are retired and live in git history at `3274e8b`. |
| 2026-11-02 | M2-01. Coverage gate and Hypothesis profiles. Raw-secret redaction property passes. `scripts/ci.py pr` exits 0 (91.35% overall, core files at 100%). |
| 2026-11-03 | M2-02. Mutation gate and `fake_binary`. `redact.py` ~97.8% kill rate (one equivalent survivor); `hashing.py` ~92.3%. `scripts/ci.py pr` exits 0. |
| 2026-11-05 | M2-04. Frozen domain types for a skill, a stage, a run, and an approval. `Verdict.approval` defaults to none. `scripts/ci.py pr` exits 0 (328 passed under coverage). |
| 2026-11-05 | M2-05. `decide` takes a `RunOutcome`. Rows 1–11 and 13 pass with no approval. `policy.py` is core: 100% branch coverage, 188/188 mutants killed. |
| 2026-11-05 | M2-06. `content_hash_v2` includes `HASH`, dotfiles, and an execute-bit mode byte. v1 `content_hash` is unchanged and still used by the pipeline. |
| 2026-11-05 | `content_hash_v2` raises `unreadable` for an unlistable directory or an unreadable file, and hashes raw path bytes. `scripts/ci.py pr` exits 0 (373 passed, 92.19% overall). |
