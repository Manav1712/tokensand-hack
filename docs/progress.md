# Skill Warden progress

Handoff for the next agent. Read this before `docs/build-guide.md`. One chat completes one step, updates this file, and stops.

## Next step

Step 19 — Mini-agent phase

## Status

| Step | State | Acceptance |
| --- | --- | --- |
| 0 Package | done | `python -m pytest tests/test_package.py -q` |
| 1 Content hash | done | `python -m pytest tests/test_hashing.py tests/test_package.py -q` |
| 2 Local registry | done | `python -m pytest tests/test_registry.py tests/test_hashing.py -q` |
| 3 Redaction | done | `python -m pytest tests/test_redact.py -q` |
| 4 Finding rows | done | `python -m pytest tests/test_findings.py tests/test_redact.py -q` |
| 5 Budget breaker | done | `python -m pytest tests/test_breaker.py -q` |
| 6 Verdict SQL | done | `python -m pytest tests/test_verdict_sql.py -q` |
| 7 Fleet memory | done | `python -m pytest tests/test_memory.py tests/test_semgrep_rule.py -q` |
| 8 Store | done | `python -m pytest tests/test_store.py tests/test_verdict_sql.py -q` |
| 9 First BLOCK path | done | `python -m pytest tests/test_first_block.py -q` |
| 10 Reader client | done | `python -m pytest tests/test_reader.py -q` |
| 11 Reader on the path | done | `python -m pytest tests/test_reader_path.py tests/test_first_block.py -q` |
| 12 Jail findings | done | `python -m pytest tests/test_findings.py tests/test_verdict_sql.py tests/test_first_block.py -q` |
| 13 Honeytoken home | done | `python -m pytest tests/test_honeytoken.py -q` |
| 14 Jail run plan | done | `python -m pytest tests/test_jail_plan.py tests/test_honeytoken.py -q` |
| 15 Sink network | done | `python -m pytest tests/test_sink.py -q` |
| 16 strace and diff | done | `python -m pytest tests/test_observe.py tests/test_observe_docker.py -q` |
| 17 Detonate a script | done | `python -m pytest tests/test_detonate.py tests/test_first_block.py -q` |
| 18 Orchestrator guards | done | `python -m pytest tests/test_orchestrator.py tests/test_first_block.py tests/test_detonate.py -q` |
| 19 Mini-agent | not started | `python -m pytest tests/test_mini_agent.py tests/test_detonate.py -q` |
| 20 Second run | not started | `python -m pytest tests/test_second_run.py tests/test_findings.py -q` |
| 21 Signing | not started | `python -m pytest tests/test_signing.py tests/test_signing_roundtrip.py -q` |
| 22 Publish | not started | `python -m pytest tests/test_publish.py -q` |
| 23 Akash client | not started | `python -m pytest tests/test_akash.py tests/test_breaker.py -q` |
| 24 Verdict page | not started | `python -m pytest tests/test_verdict_page.py -q` |
| 25 Full regression | not started | `python -m pytest tests -q` and `docker compose -f docker/compose.yaml build` |
| Gate A ClickHouse Cloud | not started | needs `CLICKHOUSE_HOST`, `CLICKHOUSE_PASSWORD`, `CLICKHOUSE_USERNAME` |
| Gate B minisign | not started | needs `~/.minisign/skill-warden.key` |
| Gate C GitHub PR | not started | needs `GITHUB_TOKEN` |
| Gate D Guild | not started | needs `GUILD_API_KEY_ID`, `GUILD_API_KEY_SECRET` |
| Gate E Akash page | not started | needs `AKASH_API_KEY` |
| Gate F AkashML | not started | needs `AKASHML_API_KEY` |

State is `not started`, `done`, `blocked`, or `failed`.

## Limitations

Carry these forward until a later log entry retires them.

- Docker is required from Step 6. If `docker info` fails, Step 6 stays blocked. Do not replace the verdict SQL with a Python copy.
- Semgrep 1.180.0 is installed in the project venv. `.venv/bin` must be on `PATH` so `semgrep` resolves. Do not request `p/agent-skills` in Step 8.
- Step 9 is green and stays on the host `semgrep` binary. The jail does not replace that path. `build_rows` accepts `jail_events` and maps honeytoken or nonce to `source=canary` / `rule_id=honeytoken`; other jail events use `source=jail`. `findings.source` includes `jail = 5`. Step 15 provides `skill_warden.sink` (`jailnet`, dnsmasq at `172.30.15.2`, `gateway_mode_ipv4=isolated`). `Orchestrator` does not start the sink or call `jail.detonate`. Step 18 adds an optional `runner(record, env) -> (events, timed_out)`. With no runner, `run` is the Step 9 body. On timeout the runner path skips the reader, calls `finish_run(run_id, "timeout")`, still calls `verdict` once, and `leave` runs in `finally`. `env` is a copy of `os.environ` without `GITHUB_TOKEN`, `CLICKHOUSE_PASSWORD`, `MINISIGN_KEY`, or `AKASHML_API_KEY`. The orchestrator still does not choose BLOCK from severity. Fleet memory is not an input to the verdict SQL. `Orchestrator.run` requires a reader collaborator. Tests use an in-process fake with `call(text) -> dict`. Production wiring to AkashML is not in this path yet. Do not call AkashML from tests.
- The sink is DNS-only. No HTTP, TLS, or catch-all on the sink until Step 17. `jailnet` is created and removed by the sink runner; an unlabeled existing `jailnet` makes `start()` raise `SinkError`. Probe image `busybox:1.36.1` must be pullable once (cached afterward).
- `observe.parse_strace` keeps `openat` / `execve` paths and `connect` destinations. A failed call’s `ret` is the errno name only (`ENOENT`), not the full strace suffix. `connect` dst parsing expects `sin_port=htons`, `inet_addr` / `inet_pton`, or `sun_path`. `events_from_diff` returns `change` and `path` only. Step 17 maps those to `build_rows` kinds. `probe_paths` stays at Step 20. Image `skill-warden-observe:step16` is local (`alpine:3.20` plus `strace`); Alpine `true` issues no `openat`, so the live parse runs `cat /etc/alpine-release` under the same `--cap-drop ALL`.
- `minisign` must be on `PATH` for Step 21. Node must be on `PATH` for Step 18.
- ClickHouse tests use a local container on port 18123. Do not point them at ClickHouse Cloud. Step 6 left `skill-warden-ch-test` running. Admin and `scanner` passwords are `test`. `scanner` can `SELECT` and `INSERT`, and can `UPDATE` only `scan_runs.status` and `scan_runs.finished_at`. `ALTER DELETE` stays denied.
- No credentials are in the repo. Human gates stay blocked until the operator sets the variables named above.
- The verdict is chosen only by `schema/verdict.sql`. A README claim is not a verdict.

## Deviations

Step 7 is fleet memory, specified in `docs/architecture.md` and `docs/build-guide.md`. The Semgrep rule, fixtures, and `semgrep.py` from the earlier Step 7 stay. Memory does not pick the verdict. Step 8 is the ClickHouse store and does not import `skill_warden.memory`.

`scanner` may `UPDATE` only `scan_runs.status` and `scan_runs.finished_at`. `finish_run` updates the one `running` row. A second insert of the same `run_id` is `duplicate_run`. `ALTER DELETE` stays denied.

Step 9 is the static BLOCK path and stays green. The jail is Steps 12–20. It lets a skill act and records the act. ClickHouse still chooses the verdict. A honeytoken or a `jail` high row is BLOCK. Step 17 is the first live detonation.

## Guide updates

| Date | Steps changed | Why |
| --- | --- | --- |
| 2026-10-09 | Execution rules | Each chat does one step and writes this file. Downstream guide edits happen only when a real deviation changes later acceptance checks. |
| 2026-10-09 | Steps 7–19 | Steps 0–6 stay. After the verdict SQL, the next integrated result is a host Semgrep scan that returns BLOCK or ALLOW from that SQL. Reader, jail, signing, and publish thicken that path. |
| 2026-10-09 | Step 7, Step 8, Step 9 regression | Step 7 is now fleet memory. Semgrep stays as already built. Step 8 does not import it. Step 9’s regression includes `tests/test_memory.py`. |
| 2026-10-09 | Gate A | `scanner` may update `scan_runs.status` and `scan_runs.finished_at` so `finish_run` does not insert a second row. |
| 2026-10-09 | Steps 12–25, architecture jail | The thin sandbox is replaced by the detonation jail. Step 12 revises findings and the `source` enum. Steps 10 and 11 are unchanged. |

## Log

### 2026-10-09 — Step 18 Orchestrator guards

- Result: done
- Acceptance: `PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest tests/test_orchestrator.py tests/test_first_block.py tests/test_detonate.py -q` exited 0 (31 passed). The first `tests/test_orchestrator.py` run failed with `TypeError: Orchestrator.__init__() got an unexpected keyword argument 'runner'` (8 failed). The same acceptance command without `.venv/bin` on `PATH` failed with `FileNotFoundError: semgrep`. Extra regression `tests/test_reader_path.py` exited 0 (3 passed). Step 17’s acceptance files were already green in this run. This chat did not change `jail.detonate`.
- Files: `tests/test_orchestrator.py`, `src/skill_warden/orchestrator.py`, `docs/progress.md`
- Limitations: a jail run is an injected runner, not `jail.detonate`. Timeout skips the reader and finishes `timeout`. `insert_findings` raising still calls `leave` and does not call `verdict`. Node was not required for this pytest step.
- Deviation: none

### 2026-10-09 — Step 16 strace and diff

- Result: done
- Acceptance: `.venv/bin/python -m pytest tests/test_observe.py tests/test_observe_docker.py -q` exited 0 (30 passed: 27 unit, 3 docker). The first unit collection failed with `ModuleNotFoundError: No module named 'skill_warden.observe'` (0 collected). Extra regression `.venv/bin/python -m pytest tests/test_observe.py tests/test_observe_docker.py tests/test_findings.py -q` exited 0 (50 passed).
- Files: `tests/test_observe.py`, `tests/test_observe_docker.py`, `src/skill_warden/observe.py`, `docs/progress.md`
- Limitations: `parse_strace_log` stitches unfinished/resumed lines by pid. Failed `ret` is the errno name only. `events_from_diff` does not assign `kind`. The `--cap-drop ALL` probe of `strace -f -e trace=openat true` exits 0 and prints only `+++ exited with 0 +++` because Alpine `true` is static. The live `openat` parse uses `cat /etc/alpine-release` with the same capability drop. Do not drop `--cap-drop ALL`.
- Deviation: none. The guide’s `true` probe still asserts exit 0. The `cat` run is an extra check, not a replacement.

### 2026-10-09 — Step 15 Sink network

- Result: done
- Acceptance: `.venv/bin/python -m pytest tests/test_sink.py -q` exited 0 (20 passed). First collection failed with `ImportError: cannot import name 'SinkError' from 'skill_warden.errors'`. Regression `.venv/bin/python -m pytest tests/test_jail_plan.py tests/test_honeytoken.py -q` exited 0 (10 passed).
- Files: `tests/test_sink.py`, `src/skill_warden/sink.py`, `src/skill_warden/errors.py`, `docker/sink/Dockerfile`, `docker/sink/entrypoint.sh`, `docs/progress.md`
- Limitations: DNS only on the sink. HTTP catch-all is Step 17. `jail.plan` unchanged. Do not import the sink from unit tests other than `tests/test_sink.py` until detonation wiring.
- Deviation: none

### 2026-10-09 — Step 14 Jail run plan

- Result: done
- Acceptance: `.venv/bin/python -m pytest tests/test_jail_plan.py tests/test_honeytoken.py -q` exited 0 (10 passed). The first run failed with `ModuleNotFoundError: No module named 'skill_warden.jail'`.
- Files: `tests/test_jail_plan.py`, `src/skill_warden/jail.py`, `docs/progress.md`
- Limitations: `plan` does not embed `skill_tar` in argv (later steps copy the tar in). `pack_skill` raises `SkillTreeError` on symlinks that resolve outside `src`. No Docker subprocess or network. Sink and detonation stay at Step 15+.
- Deviation: none

### 2026-10-09 — Step 13 Honeytoken home

- Result: done
- Acceptance: `python -m pytest tests/test_honeytoken.py -q` exited 0 (7 passed). The first run failed with `ModuleNotFoundError: No module named 'skill_warden.honeytoken'`.
- Files: `tests/test_honeytoken.py`, `src/skill_warden/honeytoken.py`, `docs/progress.md`
- Limitations: `build_home` writes only under the given `root`; ed25519 plant path is `ssh/id_ed25519.pub`. No network, no AWS/GitHub format validation. Not wired into jail or `Orchestrator` until Step 14+.
- Deviation: none

### 2026-10-09 — Step 12 Jail findings

- Result: done
- Acceptance: `PATH=".venv/bin:$PATH" .venv/bin/python -m pytest tests/test_findings.py tests/test_verdict_sql.py tests/test_first_block.py -q` exited 0 (43 passed). The first run failed with `TypeError: build_rows() got an unexpected keyword argument 'jail_events'` on the new findings tests.
- Files: `tests/test_findings.py`, `tests/test_verdict_sql.py`, `src/skill_warden/findings.py`, `schema/001_init.sql`, `docs/progress.md`
- Limitations: `schema/verdict.sql` and its `multiIf` order are unchanged. A high `source=jail` row is BLOCK via existing `high_rows`. Docker jail work still starts at Step 15. Honeytoken planting is Step 13, not wired into `Orchestrator` yet.
- Deviation: none

### 2026-10-09 — Step 11 Reader on the BLOCK path

- Result: done
- Acceptance: `python -m pytest tests/test_reader_path.py tests/test_first_block.py -q` exited 0 with `.venv/bin` on `PATH`. The first run on `tests/test_reader_path.py` alone failed with `TypeError: 'ScriptedReader' object is not callable` before `Orchestrator` accepted a `reader` argument.
- Files: `tests/test_reader_path.py`, `tests/test_first_block.py`, `fixtures/skills/prose-exfil/SKILL.md`, `src/skill_warden/orchestrator.py`, `docs/progress.md`
- Limitations: `Orchestrator.run` still returns only the SQL decision string. Reader failures map through `build_rows` (`ReaderInvalid` becomes `{}` and a `reader_invalid` row). `schema/verdict.sql` is unchanged. Step 12 is the first findings enum change.
- Deviation: none

### 2026-10-09 — Step 10 Reader client

- Result: done
- Acceptance: `python -m pytest tests/test_reader.py -q` exited 0. The first run, before `src/skill_warden/reader.py` existed, failed with `ModuleNotFoundError: No module named 'skill_warden.reader'`. `python -m pytest tests/test_first_block.py -q` exited 0 with `.venv/bin` on `PATH`.
- Files: `tests/test_reader.py`, `src/skill_warden/reader.py`, `src/skill_warden/errors.py`, `pyproject.toml`, `docs/progress.md`
- Limitations: `Reader.call` is covered only with `httpx.MockTransport`. `Orchestrator.run` does not import it. `ReaderInvalid` uses the fixed message `invalid reader response`. Unknown flag names are still rejected later by `build_rows`, not by this client.
- Deviation: none

### 2026-10-09 — Jail replaces the thin sandbox

- Result: plan only. Steps 0–9 stay done. Next step is still Step 10.
- Acceptance: documentation.
- Files: `docs/architecture.md`, `docs/build-guide.md`, `docs/progress.md`
- Limitations: do not delete the Step 9 host Semgrep path. Step 12 is the first code change to findings and the enum. Docker jail work starts at Step 15.
- Deviation: the jail lets the skill succeed against a sink and records the nonce. Akash still does not detonate skills.

### 2026-10-09 — Step 9 First BLOCK path

- Result: done
- Acceptance: `python -m pytest tests/test_first_block.py -q` exited 0. The first run, before `src/skill_warden/orchestrator.py` existed, failed with `ModuleNotFoundError: No module named 'skill_warden.orchestrator'`. Regression `python -m pytest tests/test_first_block.py tests/test_store.py tests/test_verdict_sql.py tests/test_semgrep_rule.py tests/test_findings.py tests/test_memory.py -q` exited 0.
- Files: `tests/test_first_block.py`, `fixtures/skills/audited-exfil/README.md`, `fixtures/skills/audited-exfil/SKILL.md`, `src/skill_warden/orchestrator.py`, `docs/progress.md`
- Limitations: `.venv/bin` must stay on `PATH` so the host `semgrep` binary resolves. The container `skill-warden-ch-test` is still running on port 18123. `Orchestrator.run` returns the decision string from `Store.verdict`. It does not call a reader, start Docker, or import `skill_warden.memory`. `schema/verdict.sql` is unchanged.
- Deviation: none

### 2026-10-09 — Step 8 Store

- Result: done
- Acceptance: `python -m pytest tests/test_store.py tests/test_verdict_sql.py -q` exited 0. The first run, before `src/skill_warden/store.py` existed, failed with `ModuleNotFoundError: No module named 'skill_warden.store'`.
- Files: `tests/test_store.py`, `src/skill_warden/store.py`, `src/skill_warden/errors.py`, `schema/001_init.sql`, `docs/architecture.md`, `docs/build-guide.md`
- Limitations: `scanner` may update only `scan_runs.status` and `scan_runs.finished_at`. The container `skill-warden-ch-test` is still running on port 18123. Do not import `skill_warden.memory`.
- Deviation: `finish_run` is an `ALTER UPDATE` of the existing `running` row, with `mutations_sync=1`. A second insert of the same `run_id` is `duplicate_run`. The grant is column-level. `schema/verdict.sql` is unchanged. Gate A no longer says the app user is insert-only.

### 2026-10-09 — Step 7 Fleet memory

- Result: done
- Acceptance: `python -m pytest tests/test_memory.py tests/test_semgrep_rule.py -q` exited 0. The first run, before `src/skill_warden/memory.py` existed, failed with `ModuleNotFoundError: No module named 'skill_warden.memory'`.
- Files: `tests/test_memory.py`, `src/skill_warden/memory.py`, `src/skill_warden/errors.py`
- Limitations: fleet memory is not an input to the verdict SQL. Step 8 must not import `skill_warden.memory`. `semgrep.py`, `rules/memory.yaml`, and the skill fixtures were left unchanged.
- Deviation: none

### 2026-10-09 — Step 7 redefined as fleet memory

- Result: plan only. No memory code yet.
- Acceptance: documentation. `tests/test_semgrep_rule.py` remains the passing Semgrep check from the earlier Step 7.
- Files: `docs/architecture.md`, `docs/build-guide.md`, `docs/progress.md`
- Limitations: the next agent implements `skill_warden.memory` only. Do not delete `semgrep.py`, `rules/memory.yaml`, or the skill fixtures. Do not start Step 8 in that chat.
- Deviation: Step 7’s new work is the index-and-notes store. The scan is unchanged.

### 2026-10-09 — Step 7 Local Semgrep rule

- Result: done
- Acceptance: `python -m pytest tests/test_semgrep_rule.py -q` exited 0. The first run, before `src/skill_warden/semgrep.py` existed, failed with `ModuleNotFoundError: No module named 'skill_warden.semgrep'`.
- Files: `tests/test_semgrep_rule.py`, `fixtures/skills/memory-poison/SKILL.md`, `fixtures/skills/clean-date/SKILL.md`, `rules/memory.yaml`, `src/skill_warden/semgrep.py`
- Limitations: the host `semgrep` binary must stay on `PATH` until Step 13. It lives at `.venv/bin/semgrep`. Run pytest with that directory on `PATH`. Semgrep is not a project dependency in `pyproject.toml`.
- Deviation: none

### 2026-10-09 — Step 6 Verdict SQL

- Result: done
- Acceptance: `python -m pytest tests/test_verdict_sql.py -q` exited 0. Regression `python -m pytest tests/test_package.py tests/test_hashing.py tests/test_registry.py tests/test_redact.py tests/test_findings.py tests/test_breaker.py tests/test_verdict_sql.py -q` exited 0.
- Files: `tests/test_verdict_sql.py`, `schema/001_init.sql`, `schema/verdict.sql`, `src/skill_warden/verdict.py`, `pyproject.toml`
- Limitations: container `skill-warden-ch-test` is still running on port 18123. Reuse it. The local `scanner` password is `test`. A second pytest session ignores `TABLE_ALREADY_EXISTS` when it reapplies `schema/001_init.sql`.
- Deviation: none

### 2026-10-09 — Guide order from Step 7

- Result: done
- Acceptance: documentation only. No test command.
- Files: `docs/build-guide.md`, `docs/progress.md`
- Limitations: Step 6 is still the next implementation step. The operator is writing that plan. Do not start Step 7 in this chat.
- Deviation: see Deviations. Steps 0–5 were already done and were not rewritten.

### 2026-10-09 — Step 5 Budget breaker

- Result: done
- Acceptance: `python -m pytest tests/test_breaker.py -q` exited 0
- Files: `tests/test_breaker.py`, `src/skill_warden/breaker.py`, `src/skill_warden/errors.py`
- Limitations:
- Deviation: none

### 2026-10-09 — Step 4 Finding rows

- Result: done
- Acceptance: `python -m pytest tests/test_findings.py tests/test_redact.py -q` exited 0
- Files: `tests/test_findings.py`, `src/skill_warden/findings.py`
- Limitations:
- Deviation: none

### 2026-10-09 — Step 3 Redaction

- Result: done
- Acceptance: `python -m pytest tests/test_redact.py -q` exited 0
- Files: `tests/test_redact.py`, `src/skill_warden/redact.py`
- Limitations:
- Deviation: none

### 2026-10-09 — Step 2 Local registry

- Result: done
- Acceptance: `python -m pytest tests/test_registry.py tests/test_hashing.py -q` exited 0
- Files: `tests/test_registry.py`, `src/skill_warden/registry.py`
- Limitations:
- Deviation: none

### 2026-10-09 — Step 1 Content hash

- Result: done
- Acceptance: `python -m pytest tests/test_hashing.py tests/test_package.py -q` exited 0
- Files: `tests/test_hashing.py`, `src/skill_warden/errors.py`, `src/skill_warden/hashing.py`
- Limitations: `src/skill_warden/errors.py` already exists and defines `SkillTreeError`. Later steps add to that module.
- Deviation: none

### 2026-10-09 — Step 0 Importable package

- Result: done
- Acceptance: `python -m pytest tests/test_package.py -q` exited 0
- Files: `tests/test_package.py`, `pyproject.toml`, `src/skill_warden/__init__.py`
- Limitations:
- Deviation: none

### 2026-10-09 — plan only

No code. `docs/architecture.md` and `docs/build-guide.md` are the plan. The next agent starts at Step 0.

## Template for the next entry

Copy this to the top of `## Log` when a step finishes. Update `Next step`, the status table, and Limitations in the same edit.

```markdown
### YYYY-MM-DD — Step N title

- Result: done | blocked | failed
- Acceptance: `<command>` exited 0 | non-zero
- Files: list
- Limitations: what the next agent must not assume. Empty if none.
- Deviation: none, or one paragraph. If this changes a later step, list the guide sections edited.
```
