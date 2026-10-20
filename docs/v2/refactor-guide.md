# Skill Warden v2 — refactor guide

This guide moves the hackathon code to the design in `docs/v2/architecture.md`, one tested step at a time. It follows the same discipline as `docs/build-guide.md`: one step per session, test first, update the progress file, then stop.

Read these first, in this order:

1. `docs/v2/progress.md` tells you which step is next and what earlier steps could not do.
2. `docs/v2/architecture.md` is the design. Section numbers below (§n) point into it.
3. This file: only the step named as `Next step` in `docs/v2/progress.md`.

Do not follow `docs/progress.md` or `docs/build-guide.md`. They describe the hackathon plan, and the v2 design abandons that plan. One exception: Phase 4 adapts the jail hardening in build guide Steps 19–26. When an R-step says "see build guide Step N", read that one step for its fixture details and research notes, and follow this guide wherever the two differ.

## How to execute a step

1. Activate the project venv (`source .venv/bin/activate`). The current code finds `semgrep` on `PATH`; R5 makes it resolve the binary next to `sys.executable` instead.
2. Write the tests the step names. Run the acceptance command and confirm the new tests fail for the stated reason. A test that passes on its first run proves nothing.
3. Write the minimum production code that makes the acceptance command exit 0. Then run the regression command.
4. Update `docs/v2/progress.md`: the status row, `Next step`, Limitations, and a log entry using the template there. If the step changed a later step's files, interfaces or acceptance checks, edit that later step in this guide and add a row to `Guide updates`.
5. Stop.

## Rules for every step

- The default test run (`python -m pytest -q`) uses no network and no Docker. Semgrep is allowed because it is a dependency. Docker tests carry the `docker` marker, live provider tests carry `live_llm`, and wheel tests carry `packaging`.
- Only `policy.py` decides BLOCK, ASK or ALLOW. No other module branches on severity to return a decision.
- A skill directory is data. Never add it to `sys.path`, never pass it to Semgrep as `--config`, never read config or ignore files from it, never paste its text into a log line or an exception message.
- Fixtures stay inert and obviously fake: `example.invalid`, `EXAMPLE_TOKEN`, `FAKE-CANARY`. Reuse the existing fixtures where you can. Write no live payloads.
- Real keys come from the environment only. A test that needs one is marked `live_llm` and reads the variable named in its docstring.
- Leave `demo/` untouched.
- If the same acceptance command fails twice, stop. Write the command, its last output and your hypothesis into the progress log, and leave `Next step` unchanged.

## Map: current file → v2

| Current | v2 | Step |
| --- | --- | --- |
| `pyproject.toml` | build system, declared `semgrep`, markers, extras, script | R1, R27 |
| `src/skill_warden/__init__.py` | version `0.2.0` | R27 |
| `errors.py` | drop `BudgetError` and `MemoryCapError`; add `ConfigError`, `ReaderError(kind)`, `DetonationError`, `IsolationError` | R2, R8, R9, R18 |
| `hashing.py` | keep; the algorithm is frozen | — |
| `registry.py` | replaced by `intake.py` | R4, R8 |
| `redact.py` | keep; R25 extends it to every encoding `canary.find` searches | R25 |
| `findings.py` | returns `Finding`; the Semgrep parsing moves to `static/semgrep.py`; `canary_log` and the `p/agent-skills` ruleset check are removed | R2, R5, R8 |
| `breaker.py`, `memory.py`, `verdict.py`, `store.py`, `orchestrator.py` | delete | R8 |
| `semgrep.py` | becomes `static/semgrep.py`, fail-closed | R5 |
| `reader.py` | split into `llm/reader.py`, `llm/openai_compat.py`, `llm/anthropic.py`, `llm/presets.py` | R9–R11 |
| `honeytoken.py`, `observe.py` | move to `detonate/`; lived-in home and canary registry; detail parser | R15, R19, R20 |
| `jail.py`, `sink.py` | move to `detonate/`; per-run resources; `DetonationStage`; isolation check; responsive sink; phases, agent phase and profiles | R15–R25 |
| `docker/jail/*`, `docker/sink/*` | package data under `src/skill_warden/docker/`; the sink finds its own IP; jail gains `python3`, `nodejs`, `libfaketime` and the isolation probe; sink gains TLS and all-port TCP | R15, R16, R18, R21 |
| `rules/memory.yaml` | package data `src/skill_warden/rules/`; regex fixed; liveness rule added; ruleset grows; `exfil_hosts.txt` added | R5, R21, R26 |
| `schema/001_init.sql`, `schema/verdict.sql` | delete; new package data `src/skill_warden/schema/history.sql` | R6, R8 |
| `scripts/try_sample_skill.py` | delete | R8 |
| `scripts/export_demo_traces.py` | your call: delete it, or port it to `pipeline` later. It stops working when ClickHouse goes; `demo/` keeps building from the committed `traces.json` | R8 |
| `fixtures/**` | keep; R20–R25 add jail fixtures and `fixtures/eval/manifest.json`; R26 adds rule fixtures | R20–R26 |
| `docs/architecture.md`, `docs/build-guide.md`, `docs/progress.md` | keep as the hackathon record | — |
| `.cursor/settings.json` | the ClickHouse plugin is no longer needed (your call) | R8 |
| new | `models.py`, `policy.py`, `intake.py`, `history.py`, `pipeline.py`, `config.py`, `paths.py`, `cli.py`, `report.py`, `selftest/` | R2–R14 |
| new | `canary.py`; `detonate/isolation.py`, `phases.py`, `mini_agent.py`, `profiles.py`; `scripts/eval_detonation.py` (dev only) | R18–R25 |

## Map: current test → v2

| Current test | v2 |
| --- | --- |
| `test_package.py`, `test_hashing.py`, `test_redact.py`, `test_honeytoken.py`, `test_observe.py` | keep (update import paths when modules move) |
| `test_registry.py` | → `test_intake.py` |
| `test_findings.py` | adapt to `Finding`; Semgrep-error cases move to `test_static_semgrep.py`; delete the `canary_log` and `ruleset_empty` cases |
| `test_verdict_sql.py` | → `test_policy.py` (no ClickHouse) |
| `test_store.py` | → `test_history.py` (SQLite) |
| `test_first_block.py`, `test_reader_path.py` | → `test_pipeline_static.py`, `test_pipeline_reader.py` (no ClickHouse, no Docker) |
| `test_orchestrator.py` | → `test_pipeline_guards.py` |
| `test_reader.py` | → `test_llm_reader.py`, `test_llm_openai_compat.py` |
| `test_semgrep_rule.py` | → `test_rules.py` |
| `test_breaker.py`, `test_memory.py` | delete with their modules |
| `test_jail_plan.py`, `test_detonate.py`, `test_sink.py`, `test_observe_docker.py` | adapt to `detonate/`; Docker parts marked `docker`; R18–R25 extend them |

---

# Phase 0 — Safety net

## R0 — Baseline (human)

**Goal.** Make the hackathon state recoverable before anything gets deleted.

**Do.**
1. `git init`.
2. Add a `.gitignore` covering `.venv/`, `__pycache__/`, `.pytest_cache/`, `.DS_Store`, `demo/node_modules/`, `demo/dist/`, `*.egg-info/`, `dist/` and `build/`.
3. Grep for real secrets before the first commit: `grep -rnE 'akml-|sk-ant-|ghp_[A-Za-z0-9]{20}|AKIA[0-9A-Z]{16}' --exclude-dir=.venv --exclude-dir=node_modules .`. The fixtures and honeytoken code contain fake prefixes. Read each hit before committing.
4. Commit the hackathon baseline.

**Acceptance.** `git log --oneline` shows the baseline. `python -m pytest tests -q` still reports 169 passed, with Docker running and `semgrep` on `PATH`.

---

# Phase 1 — Core without ClickHouse

## R1 — Declared dependencies and test markers

**Goal.** The default suite goes green without Docker, and Semgrep becomes a declared dependency.

**Change `pyproject.toml`.**
- Add `[build-system]` with `requires = ["hatchling"]` and `build-backend = "hatchling.build"`.
- Set `[tool.hatch.build.targets.wheel] packages = ["src/skill_warden"]`.
- Set `requires-python = ">=3.11"`.
- Set `dependencies = ["httpx", "clickhouse-connect", "semgrep>=1.180,<2"]`. `clickhouse-connect` stays until R8.
- Add the extra `dev = ["pytest"]`.
- Register three markers, `docker`, `live_llm` and `packaging`, and set `addopts = "-m 'not docker and not live_llm and not packaging'"`.

**Mark the tests that need Docker.**
- Module-level `pytestmark = pytest.mark.docker` in `test_verdict_sql.py`, `test_store.py`, `test_first_block.py`, `test_reader_path.py`, `test_sink.py` and `test_observe_docker.py`.
- In `test_detonate.py`, mark only the four tests that use the `scanner` or `_docker_sink_ready` fixtures.

**Test first.** None. This step is configuration.

**Acceptance.**

```bash
pip install -e '.[dev]'
DOCKER_HOST=unix:///nonexistent.sock python -m pytest -q
python -m pytest -m docker -q   # with Docker running: the old Docker suite still passes
```

The first test command must exit 0 even though it cannot reach Docker.

## R2 — Domain types

**Goal.** Add `models.py` with the types in §7.1, and `Finding` conversion helpers so the old dict rows can be bridged.

**Interfaces.**
- `Severity` and `Source` are `StrEnum`s.
- `Finding` has `evidence_hash` as a property (the sha256 of `excerpt`), `as_dict()`, and the classmethod `from_row(dict)`. `from_row` accepts today's `build_rows` dicts.
- Also add `FileEntry`, `SkillRecord`, `StageResult` (with a non-serialized `secrets: tuple[str, ...] = ()`), `RunOutcome`, `Verdict` and `Report`.

**Test first: `tests/test_models.py`.**
- The enum values are exactly the strings in §7.1.
- `Finding(...).evidence_hash == sha256(excerpt)`.
- `from_row(build_rows(...)[i]).as_dict()` round-trips every key that today's rows carry.
- The dataclasses are frozen: assigning to a field raises.

**Fail means.** `ModuleNotFoundError: skill_warden.models`.

**Acceptance.** `python -m pytest tests/test_models.py -q`
**Regression.** `python -m pytest -q`

## R3 — Policy as a pure function

**Goal.** Add `policy.decide(outcome) -> Verdict`, implementing the table in §12. It does no I/O.

**Test first: `tests/test_policy.py`.**
- Parametrize over every row of the "port of the 19 ClickHouse cases" table and the "new cases" table in §12. Assert both `decision` and `reason`.
- Assert `detail` is the deciding finding's `rule_id`, for example `tool_error` with detail `semgrep_failed`.
- Monotonicity: for each base case that contains a canary, error, high or critical finding, adding any one extra finding drawn from every source × severity combination leaves the decision BLOCK.
- Determinism: the same `RunOutcome` decided twice gives equal verdicts.

**Fail means.** `ModuleNotFoundError: skill_warden.policy`, or a case returns the wrong decision.

**Acceptance.** `python -m pytest tests/test_policy.py -q`
**Regression.** `python -m pytest -q`

Note: `schema/verdict.sql` stays until R8. Don't call it from the new code.

## R4 — Intake

**Goal.** Add `intake.py` with `discover(paths, *, max_depth=4) -> list[Path]` and `load_skill(path, caps) -> tuple[SkillRecord, list[Finding], Path]`. The third value is the normalized copy (§8). The caller owns that temporary directory; tests use `tmp_path`.

**Test first: `tests/test_intake.py`.** Port the `test_registry.py` sorting test to `discover`.
- `discover` finds `a/SKILL.md` and `b/c/SKILL.md` under a root. It treats `a/sub/SKILL.md` as part of `a`, not a second skill. A path given as a `SKILL.md` file yields its parent. A root with no skills yields `[]`.
- A symlink inside the skill → a `symlink` error finding, `content_sha256 is None`, and no traceback.
- A root that is a symlink to a skill → resolved, with an `info` finding.
- Caps: 501 files, total bytes over the limit, or one file over the limit → `too_large` (error).
- A PNG in `assets/` → `binary_file` (info). An ELF header under `scripts/` → `opaque_binary` (medium). A Latin-1 `notes.md` → `undecodable_text` (medium). None of these raise.
- A `SKILL.md` containing U+200B → `obfuscation.unicode` (medium), and the normalized copy has no U+200B. A non-breaking space alone → no finding.
- For a clean tree, `content_sha256 == hashing.content_hash(path)`.
- Frontmatter `name` is read without a YAML dependency. A missing frontmatter → `frontmatter_invalid` (info).

**Fail means.** `ModuleNotFoundError: skill_warden.intake`.

**Acceptance.** `python -m pytest tests/test_intake.py tests/test_hashing.py -q`
**Regression.** `python -m pytest -q`

## R5 — Static stage, fail-closed

**Goal.** Add `static/semgrep.py` with `SemgrepStage.run(skill, workdir, deadline) -> StageResult`, following §9. Move the rules to `src/skill_warden/rules/memory.yaml`, fix the folded regex, and add `rules/liveness.yaml`. Load rules with `importlib.resources`.

**Interfaces.**
- `resolve_semgrep(config_path: str | None) -> Path | None`.
- `SemgrepStage(rules_dirs, extra_configs, timeout, run=subprocess.run)`. `run` is injectable so failure modes can be tested without breaking a real install.

**Test first.**
- `tests/test_static_semgrep.py`, with a fake `run`, one test per row of the §9.3 table:
  - exit 2 with `results: []` → `semgrep_failed`, never `semgrep.ok` (today this case yields ALLOW);
  - exit 7 → `semgrep_failed`;
  - `FileNotFoundError` → `semgrep_unavailable`;
  - `TimeoutExpired` → `semgrep_timeout`;
  - empty stdout → `semgrep_failed`;
  - an `errors[]` entry at level `error` → `semgrep_error`;
  - a target missing from `paths.scanned` → `target_not_scanned`;
  - the liveness hit missing → `semgrep_liveness_failed`;
  - the liveness hit present → filtered out of the findings;
  - the argv contains no directories and includes `--metrics=off` and `--disable-version-check`.
- `tests/test_rules.py`, with real Semgrep, ported from `test_semgrep_rule.py`:
  - `memory-poison` → high;
  - `clean-date` → `semgrep.ok`;
  - `append the note to ./MEMORY.md` → high (fails on today's rule);
  - a `.semgrepignore` or `.semgrep.yml` shipped in the skill does not hide the match.
- Resolution: with a fake `sys.executable` directory that contains a `semgrep` script, it wins over `PATH`.

**Implement.** Also update the `RULES` constant in tests that still drive the old orchestrator. They are removed in R8.

**Fail means.** `ModuleNotFoundError`, or `semgrep.ok` emitted on a failing run.

**Acceptance.** `python -m pytest tests/test_static_semgrep.py tests/test_rules.py -q`
**Regression.** `python -m pytest -q`

## R6 — History on SQLite

**Goal.** Add `history.py` and `src/skill_warden/schema/history.sql`, following §13.

**Interfaces.**
- `History(path: Path)`.
- `record(report: Report, secrets: Sequence[str]) -> None`, which runs in one `BEGIN IMMEDIATE` transaction.
- `list(limit) -> list[...]`.
- `get(run_id) -> Report | None`.
- `verify() -> list[str]`, which returns the bad `run_id`s and is empty when the chain is intact.

**Test first: `tests/test_history.py`.** Port the cases from `test_store.py`.
- Record a clean report, then read back the same verdict and findings.
- An excerpt containing a secret raises `RedactionError`, and `SELECT count(*)` for that run is 0 in all three tables.
- Three runs chain correctly: each `prev_hash` equals the previous `payload_hash`, and `verify()` returns `[]`.
- A raw `UPDATE verdicts SET decision='ALLOW'` makes `verify()` report that run.
- Two `History` objects on one file write sequentially without forking the chain.

**Fail means.** `ModuleNotFoundError: skill_warden.history`.

**Acceptance.** `python -m pytest tests/test_history.py -q`
**Regression.** `python -m pytest -q`

## R7 — One pipeline

**Goal.** Add `pipeline.scan_skill(path, settings, *, stages, history=None, clock=time.monotonic) -> Report`, following §7. A stage is any object with `name` and `run(skill, workdir, deadline) -> StageResult`. Requested stages arrive from the caller already built. The pipeline never decides; it calls `policy.decide`.

**Test first.**
- `tests/test_pipeline_static.py` (real Semgrep, temporary history, no Docker), ported from `test_first_block.py`:
  - `memory-poison` → BLOCK `high_finding`;
  - `clean-date` → ALLOW `clean`, with only the `semgrep.ok` finding;
  - `audited-exfil` → BLOCK `high_finding`, and the reason is not the README sentence;
  - the returned verdict equals what history stored.
- `tests/test_pipeline_reader.py`, ported from `test_reader_path.py`. A scripted reader stage returns findings or invalid output:
  - `prose-exfil` + `credential_exfil` → BLOCK `high_finding`;
  - `clean-date` + `false_safety_claim` → ASK `medium_only`;
  - a `{"decision": "ALLOW"}` body → BLOCK `reader_error`.
- `tests/test_pipeline_guards.py`, ported from `test_orchestrator.py`, using fakes:
  - global timeout → BLOCK `timeout`, and the reader is not called;
  - a stage raising → BLOCK `not_finished`, and the scan still returns a report;
  - `decide` is called once;
  - short-circuit: static high → the reader stage is not called, unless `full=True`;
  - a requested reader that returns an empty `StageResult` → BLOCK `reader_missing`;
  - an intake error → static, reader and detonation all `skipped`;
  - a history write failure → the same verdict, plus a warning;
  - no stage receives `os.environ` in any form.

**Fail means.** `ModuleNotFoundError: skill_warden.pipeline`, or a decision made outside `policy`.

**Acceptance.** `python -m pytest tests/test_pipeline_static.py tests/test_pipeline_reader.py tests/test_pipeline_guards.py -q`
**Regression.** `python -m pytest -q`

## R8 — Remove ClickHouse and dead modules

**Goal.** Delete what §3.1 removes. Afterwards the suite has no ClickHouse and no Docker dependency outside the `docker` marker.

**Delete.**
- Modules: `store.py`, `verdict.py`, `breaker.py`, `memory.py`, `registry.py`, `orchestrator.py`, `semgrep.py` (replaced by `static/semgrep.py`).
- The function `jail.detonate()`. It imports `skill_warden.semgrep`, calls `build_rows(semgrep=…)` and writes through `Store`, so it can't survive this step. Keep the rest of `jail.py` (`plan`, `pack_skill`, `phase_commands`, `events_from_observation`, `container_argv`); R17 rebuilds detonation as a stage.
- `schema/001_init.sql`, `schema/verdict.sql`, `scripts/try_sample_skill.py`.
- Tests: `test_verdict_sql.py`, `test_store.py`, `test_first_block.py`, `test_reader_path.py`, `test_orchestrator.py`, `test_breaker.py`, `test_memory.py`, `test_registry.py`, and the four ClickHouse-backed `docker` tests in `test_detonate.py`. Keep that file's unit tests.

Between R8 and R17 there is no end-to-end detonation. Record that under Limitations in `docs/v2/progress.md`.

**Adapt.**
- In `findings.py`, remove the `canary_log`, `rules_requested` and `rules_loaded` parameters and the Semgrep parsing, and return `Finding`s.
- In `test_findings.py`, delete the `canary_log` and `ruleset_empty` cases, move the Semgrep-skip cases to `test_static_semgrep.py`, and compare against `finding.as_dict()`.
- Remove `BudgetError` and `MemoryCapError` from `errors.py`.
- Drop `clickhouse-connect` from `pyproject.toml`.
- Decide about `scripts/export_demo_traces.py` (see the file map).

**Test first.** None new. The deletions must leave everything green.

**Acceptance.**

```bash
python -m pytest -q
grep -rniE 'clickhouse|akash|guild|minisign|breaker' src tests pyproject.toml   # no output
pip uninstall -y clickhouse-connect && python -m pytest -q
```

After this step you can remove the old test container: `docker rm -f skill-warden-ch-test`.

---

# Phase 2 — Provider-agnostic reader

## R9 — Reader core

**Goal.** Add `llm/reader.py`, following §10.2–10.6:
- `build_request(skill, workdir, cfg) -> tuple[ReaderRequest, str]`, where the second value is the canary;
- `parse_response(text, canary) -> tuple[list[str], list[str]]`, which raises `ReaderError("invalid" | "canary")`;
- `ReaderStage(client, cfg)`, which implements the stage protocol;
- the `ReaderClient` protocol and `ReaderError(kind, detail)`.

**Test first: `tests/test_llm_reader.py`.**
- **Payload:** `SKILL.md` comes first and each file has its `=== FILE: … ===` header. Binaries appear by name only. The boundary token differs between calls. The skill text appears only inside the boundaries.
- **Cap:** a payload over `max_input_chars` → `reader_input_too_large`, and the client is never called.
- **Parsing:**
  - one `json` fence is unwrapped; two fences → invalid; prose → invalid;
  - extra key → invalid; unknown flag → invalid; non-string evidence → invalid;
  - a valid response with no flags → `reader.ok`.
- **Canary and refusals:** a response echoing the canary → `reader_canary_echoed`. `ReaderError` kinds `unavailable` and `refused` map to `reader_unavailable` and `reader_refused`.
- **Leaks:** port today's test that skill text never appears in exception messages.
- **Evidence:** excerpts are redacted and capped at 200 characters, reusing today's `_reader_rows` behavior.

**Fail means.** `ModuleNotFoundError: skill_warden.llm.reader`.

**Acceptance.** `python -m pytest tests/test_llm_reader.py -q`
**Regression.** `python -m pytest -q`

## R10 — OpenAI-compatible adapter and presets

**Goal.** Add `llm/openai_compat.py` (httpx) and `llm/presets.py`, following §10.7. Delete `reader.py` along with its AkashML defaults (`https://api.akashml.com/v1`, `openai/gpt-oss-120b`), delete `tests/test_reader.py` (its cases now live in `test_llm_reader.py` and `test_llm_openai_compat.py`), and remove every `AKASHML_API_KEY` reference.

**Test first: `tests/test_llm_openai_compat.py`** (`httpx.MockTransport`, injected sleep).
- **`openai` preset:** sends `max_completion_tokens`, plus `response_format` of type `json_schema` whose `json_schema` object has a non-empty `name`, `strict: true` and the §10.6 schema. Without `name`, the first live call fails with a 400. `Authorization: Bearer` comes from the configured environment variable.
- **`ollama` preset:** sends `max_tokens` and `response_format: {"type": "json_object"}`. With no key configured, it sends no `Authorization` header.
- **Never sent:** `tools` and `tool_choice`, in any preset. `temperature` appears only when configured.
- **Response handling:**
  - `finish_reason: "length"` → `invalid`;
  - a non-null `message.refusal` → `refused`;
  - `content: null` → `invalid`.
- **Errors and retries:**
  - 401 or 404 → `unavailable`, with no retry;
  - 429 with `Retry-After: 1` followed by 200 → success after one injected sleep of 1 s;
  - 500 three times → `unavailable` after exactly two retries;
  - `httpx.ConnectError` → `unavailable`;
  - the variable named by `api_key_env` being unset → `unavailable`, with no request sent.
- **Presets:** an unknown provider → `ConfigError`. `model` missing → `ConfigError`.

**Fail means.** `ModuleNotFoundError`, or `tool_choice` present in a request body.

**Acceptance.** `python -m pytest tests/test_llm_openai_compat.py tests/test_llm_reader.py -q`
**Regression.** `python -m pytest -q`
**Optional live check** (marked `live_llm`, needs a running Ollama and a pulled model): `python -m pytest -m live_llm tests/test_llm_live.py -q`

## R11 — Anthropic adapter (optional extra)

**Goal.** Add `llm/anthropic.py`, following §10.8, using the official `anthropic` SDK. Add the extra `anthropic = ["anthropic>=<current major>"]` to `pyproject.toml`; check PyPI for the current major. Get call shapes and exception class names from the SDK's README; don't guess them. The SDK uses `httpx2`, so never pass core `httpx` objects into it.

**Test first: `tests/test_llm_anthropic.py`.** Inject a fake SDK client through a `client_factory` argument and record the keyword arguments of `messages.create`.
- **Request:** `model`, `max_tokens`, `system` and `messages` are present. `output_config["format"]` is `{"type": "json_schema", "schema": READER_SCHEMA}`. `temperature` is absent. `thinking` is absent.
- **Effort:** when `effort` is set, it appears as `output_config["effort"]`.
- **Fallbacks:**
  - With `refusal_fallback` on and a supported model, the adapter uses the beta namespace: `client.beta.messages.create` with `betas=["server-side-fallback-2026-07-01"]` and `fallbacks="default"`. Otherwise it uses `client.messages.create` and sends neither field. They are never sent for Haiku 5.5.
  - A response that contains a `fallback` content block, or a `fallback_message` entry in `usage.iterations`, still returns the text. It also yields `reader_primary_refused` (medium) and the answering model.
  - The text comes from the first `type == "text"` block, not `content[0]`.
- **Stop reasons:** `end_turn` → returns the text. `max_tokens` → `invalid`. A final `refusal` → `refused`, with the category in the detail.
- **Missing extra:** with `anthropic` not importable (monkeypatch it in `sys.modules`), building the client → `unavailable`, and the message names `pip install 'skill-warden[anthropic]'`.
- **Error mapping:** use the SDK's own exception classes as its README documents them. Authentication, permission, not-found, rate-limit, server, connection and timeout errors → `unavailable`. Bad request → `unavailable`, with the API message.
- **Live test** (`live_llm`, needs `ANTHROPIC_API_KEY`): one `doctor --llm`-style call on `selftest/clean`.

**Fail means.** A `temperature` or `thinking` key reaches `messages.create`.

**Acceptance.** `pip install -e '.[dev,anthropic]' && python -m pytest tests/test_llm_anthropic.py -q`
**Regression.** `python -m pytest -q`. This must also pass without the extra installed.

---

# Phase 3 — Config and CLI

## R12 — Config and paths

**Goal.** Add `config.py` (dataclasses, `tomllib`, strict validation, precedence) and `paths.py`, following §14.

**Test first: `tests/test_config.py`.**
- **Precedence:** defaults < file < `SKILL_WARDEN_*` env < flags.
- **Validation:** an unknown key → `ConfigError` naming `llm.modle`; a wrong type → `ConfigError`.
- **`--llm` parsing:** `ollama:qwen2.5:7b` parses as provider `ollama` and model `qwen2.5:7b`.
- **No implicit project config:** a `.skill-warden.toml` in the current directory is ignored.
- **Paths:** XDG variables are honored, and `%APPDATA%` / `%LOCALAPPDATA%` are used when `os.name == "nt"` (monkeypatched).
- **Keys:** `api_key_env` stores a variable name. A config field that looks like a literal key (`sk-…`) is rejected, with a message telling the user to use `api_key_env`.

**Acceptance.** `python -m pytest tests/test_config.py -q`
**Regression.** `python -m pytest -q`

## R13 — `skill-warden scan`

**Goal.** Add `cli.py` (argparse, with `main(argv) -> int` and no `sys.exit` inside it) and `report.py` (text and JSON rendering), following §6. Add `[project.scripts] skill-warden = "skill_warden.cli:main"` to `pyproject.toml`, through a thin wrapper that calls `sys.exit(main(sys.argv[1:]))`, and re-run `pip install -e '.[dev]'` so the command exists.

**Test first: `tests/test_cli_scan.py`.** Use a temporary `SKILL_WARDEN_HOME` and the real Semgrep.
- **Exit codes:** `clean-date` → 0, `memory-poison` → 20, a medium-only fixture → 10, a path containing no skills → 2, a malformed config → 2.
- **Multiple paths:** the exit code is the worst verdict, and the JSON `summary.counts` is correct.
- **JSON:** the `--format json` envelope matches `skill-warden/scan@1` (keys and types, as a snapshot).
- **Coverage:** with no `[llm]` config, `reader.status == "off"` and the text output says "static only".
- **`--no-history`** writes no database.
- **Isolation:** a stage that raises for one skill doesn't stop the next skill from being scanned.
- **Secrets:** no API-key value appears in stdout, stderr or the database. Set a fake one in the environment to check.
- **Rendering redaction:** a report whose findings would render a run secret is BLOCK `not_finished`, and the secret appears in no output.

**Acceptance.** `python -m pytest tests/test_cli_scan.py -q`, then `skill-warden scan fixtures/skills/memory-poison; echo $?` prints a BLOCK report and `20`.
**Regression.** `python -m pytest -q`

## R14 — `init`, `doctor`, `history`, `show`

**Goal.** Implement the rest of §6.1 and §6.5. Ship `src/skill_warden/selftest/clean/` and `selftest/memory/` as package data.

**Test first: `tests/test_cli_other.py`.**
- **`init`:** writes the template; refuses to overwrite without `--force`; the template parses with `tomllib`; it contains no key values.
- **`doctor`:** passes the static self-test (`clean` → ALLOW, `memory` → BLOCK). With Semgrep unresolvable (monkeypatched), it exits non-zero and says why. `--llm` with a fake reader announces the call before making it.
- **`history`:** lists runs. `--verify` reports a tampered row.
- **`show RUN_ID`:** prints the stored JSON.

**Acceptance.** `python -m pytest tests/test_cli_other.py -q`, then `skill-warden doctor; echo $?` prints `0`.
**Regression.** `python -m pytest -q`

---

# Phase 4 — Detonation

R15–R17 port the hackathon jail into a per-run, opt-in stage. R18–R25 add the jail hardening that `docs/build-guide.md` Steps 19–26 specify, adapted to v2: no ClickHouse, no `source=policy` row, and `policy.decide` instead of verdict SQL. When a step here says "see build guide Step N", read only that step for its fixture details and research notes. Where it differs from this guide, this guide wins.

Rules for every Phase 4 step, on top of the general rules:

- `policy.py` stays the only decider, and the decisions stay BLOCK, ASK and ALLOW. Do not add a fourth decision, and do not change `policy.py` or the §12 table to make a fixture pass.
- v2 has no `policy` source. When an isolation check fails, a planned phase or script did not run, or coverage is incomplete, the stage emits a `jail` finding at severity `error` (`isolation_failed`, `coverage_incomplete`). §12 row 6 turns that into BLOCK `tool_error`, with the rule id as `detail`. A detonation that observed nothing is never ALLOW: rows 6 and 10 cover it.
- Touching a canary is BLOCK `canary`, whatever the skill says it is for. A skill's description is a claim, not evidence.
- When the global clock expires, the result is BLOCK `timeout` (row 1). A phase timeout is a `delay` finding at high (§11.5). Both are BLOCK.
- Real-format credential values are generated at run time inside the run's `TemporaryDirectory`. They never appear in a fixture, a test file, history, rendered output or the eval manifest. Fixtures refer to planted values by path or by environment variable name. Raw strace and sink logs live only in memory. The stage writes no log to disk.
- Docker tests that assert jail behavior call `pipeline.scan_skill(..., full=True)`. Without it, a static `high` finding (for example R26's outbound-transfer rule on `steal-key`) short-circuits the jail, and the test stops exercising it.
- A detection counts only if a fixture exercises it in the jail. A parser unit test doesn't prove that the live run sees the event.
- When a step changes a module an earlier step built, it says so in a **Revises.** line. Keep earlier assertions. Add new tests next to them. Change an earlier test only where a step names the exception.
- Fixtures simulate harm and nothing more: they touch only planted values and the sink, and they use `example.invalid` hosts.

## R15 — Package data and content-addressed images

**Goal.**
- Move `docker/jail` and `docker/sink` into `src/skill_warden/docker/`.
- Move `jail.py`, `sink.py`, `observe.py` and `honeytoken.py` into `src/skill_warden/detonate/`.
- Add `detonate/images.py` with `context_tag(name) -> str` and `ensure_image(name, run=…)`.
- Use `importlib.resources.as_file` for build contexts. Remove every `parents[2]` lookup.
- Give the build contexts everything R18–R24 need, so the content-addressed tags change once, here, and not in every later step:
  - The jail image gains `python3`, `nodejs`, `libfaketime` and `docker/jail/isolation-probe.sh`. Until R18 the probe script only prints its fields.
  - The sink image gains `openssl` and `iptables`.
  - Both base images are pinned by digest (§11.3).

**Test first: `tests/test_detonate_images.py`** (no Docker).
- The tag is stable for identical context bytes and changes when one byte changes.
- `ensure_image` calls `docker build` only when `docker image inspect` fails, checked with a fake `run`.
- No module under `src/skill_warden/detonate/` references `parents[` or `Path.cwd()`. Check this by grepping the source in the test.
- The jail context contains `isolation-probe.sh`, and its `Dockerfile` names `python3`, `nodejs` and `libfaketime`.
- Every `FROM` line carries `@sha256:`.
- The old `test_jail_plan.py`, `test_honeytoken.py` and `test_observe.py` pass under the new import paths.

**Acceptance.** `python -m pytest tests/test_detonate_images.py tests/test_jail_plan.py tests/test_honeytoken.py tests/test_observe.py -q`
**Regression.** `python -m pytest -q`, then `python -m pytest -m docker -q` with Docker running.

## R16 — Per-run network and sink

**Goal.** Implement §11.4.
- `sink.start(run_id) -> SinkSession(network, container, ip)` creates `sw-<run8>` and `sw-sink-<run8>` with run-scoped labels, and reads the sink IP from `docker inspect`.
- The sink entrypoint finds its own IP. It no longer receives `SINK_IP`.
- `stop(session)` removes only that run's resources.
- `gc(older_than=3600)` removes stale labeled resources.
- `http_log(session)` and `dns_log(session)` read from that session only. Delete `_cached_http_log`.
- Give the log readers one shape, `logs(session) -> dict[str, str]`, keyed `dns` and `http`. R21 adds `tls` and `tcp` under the same call, and R20 searches every key.

**Test first.**
- `tests/test_sink_unit.py` (no Docker): there is no module-level log cache, and a failed read for one session never returns another session's data. The `docker network create` argv contains `--internal`, `--ipv6=false` and `gateway_mode_ipv4=isolated`, and no `--subnet`.
- `tests/test_sink.py` (`docker`): port today's tests to per-run sessions. Add:
  - two concurrent sessions, each resolving `evil.example` to its own sink IP;
  - stopping one session leaves the other running;
  - `gc` removes a session whose `skill-warden.created` label is old;
  - 1.1.1.1 is unreachable from both.

**Acceptance.** `python -m pytest tests/test_sink_unit.py -q && python -m pytest -m docker tests/test_sink.py -q`
**Regression.** `python -m pytest -q`

## R17 — Detonation as a pipeline stage

**Goal.** Add `detonate/stage.py` with `DetonationStage.run(skill, workdir, deadline) -> StageResult`, following §11.
- Build the honeytoken home with a fresh nonce in a new `TemporaryDirectory`, and pack the skill with `pack_skill`.
- Start the per-run sink, create and harden the jail, stream the skill and home in, and run the phase under `strace`.
- Collect and map events with the existing `events_from_observation` and `findings` jail mapping.
- Emit `jail.ok` when there are no `jail` findings. Return the plants and the nonce in `StageResult.secrets`. R19 widens this to the whole canary registry.
- Tear down in `finally`, including the `TemporaryDirectory`.
- Map Docker being missing or the isolated mode being unsupported → `detonation_unavailable`, and any failed step → `detonation_failed`.
- Delete `jail.detonate` and the old runner injection. The stage takes no `env`.
- Give the stage one ordered hook list, `pre_skill_checks`, which runs after the jail container exists and before any skill bytes are streamed in. It is empty in this step. R18 fills it.

**Test first.**
- `tests/test_detonation_stage.py`, with a fake Docker runner:
  - call order;
  - `docker rm` and `stop(session)` run even when a step raises;
  - no `-v`, no `docker.sock`, and no host environment variable in any argv;
  - a failed `docker info` → `detonation_unavailable`;
  - a `pre_skill_checks` hook runs before the skill tar is streamed;
  - the `TemporaryDirectory` no longer exists after `run` returns or raises.
- `tests/test_detonate.py` (`docker`), through `pipeline.scan_skill(..., full=True)` with a temporary history:
  - `steal-key` → BLOCK with reason `canary` or `high_finding`;
  - `clean-date` → ALLOW `clean`, with `jail.ok`;
  - the nonce is absent from every stored excerpt;
  - the sink HTTP log for that run records the POST to `/collect`.

**Acceptance.** `python -m pytest tests/test_detonation_stage.py -q && python -m pytest -m docker tests/test_detonate.py -q`, then `skill-warden scan --detonate fixtures/skills/steal-key; echo $?` prints `20`.
**Regression.** `python -m pytest -q`

## R18 — Isolation check, fail closed

See build guide Step 19.

**Revises.** R17's `DetonationStage` (`pre_skill_checks` and the host check before any container starts), `jail.plan` (adds `--runtime=runsc` when Docker lists it), and `errors.py` (`IsolationError`, a subclass of `DetonationError`).

**Goal.** Add `detonate/isolation.py` with three checks. Each raises `IsolationError` naming the check.
1. `check_host(components_json, runtimes_json, require_runsc=False)`. Its inputs are `docker version --format '{{json .Server.Components}}'` and `docker info --format '{{json .Runtimes}}'`. It raises when:
   - runc is below 1.2.8 on 1.2.x, below 1.3.3 on 1.3.x, below 1.4.0-rc.3 on 1.4 pre-releases, or below 1.2 at all. These floors fix CVE-2025-31133, CVE-2025-52565 and CVE-2025-52881;
   - `require_runsc` is set and `runsc` isn't listed.
2. `check_container(inspect_json)`. It raises on any of: `Privileged`; `host` for PID, IPC or network mode; a network other than this run's `sw-<run8>`; any mount that isn't one of the plan's tmpfs mounts; any mount source containing `docker.sock`.
3. `check_inside(probe_text)`. Its input is the stdout of `/warden/isolation-probe.sh`, run inside the jail as uid 10001 through the same `su` the phases use. Running it as root would show the `SETUID`/`SETGID` bounding set, not what the skill gets. It raises unless all of these hold:
   - effective and ambient capabilities are zero;
   - `NoNewPrivs` is 1;
   - `Seccomp` is 2;
   - there is no `docker.sock`;
   - the `/` entry in `mountinfo` carries `ro`. Read this from the mount table. A failed write proves nothing, because uid 10001 can't write to `/` either way;
   - the uid isn't 0;
   - a direct `curl --noproxy '*'` to 1.1.1.1 fails to connect or times out (exit 7 or 28).

gVisor isn't the default. `jail.plan` uses `runsc` only when `docker info` lists it. Otherwise it uses hardened runc, and `check_host` enforces the floor. The probe runs inside whichever runtime is used.

When any check raises, the stage streams no skill bytes. It returns `StageResult(status="failed")` with one finding, `jail` / `isolation_failed` / error, whose excerpt is the failed check's name. Never put raw `docker inspect` output into a finding, a report or an exception message. After R19, its `Config.Env` holds bait values. `isolation.report()` returns only check names with pass or fail, plus the runc and runtime version strings. `doctor --docker` prints that report (this revises R14).

**Known blocker on this machine.** On 16 October 2026 this Mac reported Docker Engine 28.5.1 with runc 1.2.5, which is below the floor. The docker test fails until the operator updates Docker Desktop. Mark R18 `blocked` in `docs/v2/progress.md`, record the runc version you saw, and stop. Do not lower the floor, add an override, or deselect the test. While R18 is blocked, R26 and R27 don't depend on Phase 4 and may run out of order. Record that in the log if you do it.

**Test first.**
- `tests/test_isolation.py` (no Docker), one test per case:
  - 1.2.5 raises and 1.2.8 passes;
  - 1.3.2 raises and 1.3.3 passes;
  - 1.4.0-rc.2 raises and 1.4.0-rc.3 passes;
  - 1.1.12 raises;
  - `require_runsc` with only runc listed raises;
  - a fully correct probe text passes, and each bad field raises on its own;
  - inspect JSON with `Privileged: true` raises, and so does a `docker.sock` mount;
  - `report()` contains no environment value.
- `tests/test_detonation_stage.py`: a fake `check_host` that raises means the skill tar is never streamed, and the finding is `isolation_failed`.
- `tests/test_policy.py`: `jail` / `isolation_failed` / error plus `semgrep.ok` → BLOCK `tool_error`, with detail `isolation_failed`.
- `tests/test_isolation_docker.py` (`docker`): run the probe in a jail built from `jail.plan` and assert that `check_inside` and `check_container` pass. Run `check_host` on this machine.

**Fail means.** `ModuleNotFoundError: skill_warden.detonate.isolation`, a bad probe that passes, or skill bytes streamed after a failed check.

**Acceptance.** `python -m pytest tests/test_isolation.py tests/test_detonation_stage.py tests/test_policy.py -q && python -m pytest -m docker tests/test_isolation_docker.py tests/test_detonate.py -q`
**Regression.** `python -m pytest -q`

## R19 — A lived-in home and the canary registry

See build guide Step 20.

**Revises.** `detonate/honeytoken.py` and `jail.plan`. Every existing plant stays at its current path, and `search_nonce` stays as written. `steal-key` reads `~/aws/credentials`, so that path must keep working.

**Goal.**
- `build_home(root, nonce, rng=None, now=None) -> list[Plant]` adds plants at the canonical paths real tools read. The full list is in build guide Step 20: cloud, SSH, git-forge, package-registry, container and cluster credentials, an agent config, a project `.env`, a wallet file and a browser credential store.
- Values are generated per run from `rng`, in the real format. Each one must pass its format check: the GitHub token's CRC32 checksum verifies, the SSH key has OpenSSH armor and an `openssh-key-v1\0` body, and the kubeconfig parses. A format-valid value can't also contain the nonce, so:
  - `honeytoken.registry(plants, env_baits) -> CanaryRegistry` holds every planted value, every bait value and the nonce;
  - the nonce stays in `MEMORY.md` and in the old plants.
- `honeytoken.env_baits(rng) -> dict[str, str]` returns the bait variables listed in build guide Step 20. It never uses the name of a real Warden secret, or the configured `api_key_env`. `jail.plan(..., extra_env=None)` appends each bait as `-e`. A bait value only shows up when it leaves through egress, argv or a file. R20 covers those channels.
- Wear and tear, because an empty home is a sandbox tell: shell history, `.gitconfig` with an `example.invalid` email, a small git project, a pip cache. Spread mtimes between 30 and 400 days before `now`.
- `DetonationStage` returns every registry value in `StageResult.secrets`, so §7.4 redaction, history and the render check all cover them.

**Test first.** Extend `tests/test_honeytoken.py`, one test per behavior:
- every canonical path exists under `root`, and nothing is written outside it;
- each value matches its format, and the GitHub checksum verifies;
- the kubeconfig parses, using a minimal parser in the test (no PyYAML);
- two seeds share no value;
- the registry contains every plant value, every bait value and the nonce;
- the bait names exclude Warden's own secret names;
- mtimes are older than `now - 30 days`;
- the old `aws/credentials` plant still contains the nonce.

Extend `tests/test_jail_plan.py`: `extra_env` lands as `-e` pairs, and the test machine's home is still absent. Extend `tests/test_detonation_stage.py`: `StageResult.secrets` equals the registry.

**Fail means.** A missing canonical path, a value that fails its format, two runs sharing a value, or a registry value missing from `secrets`.

**Acceptance.** `python -m pytest tests/test_honeytoken.py tests/test_jail_plan.py tests/test_detonation_stage.py -q && python -m pytest -m docker tests/test_detonate.py -q`
**Regression.** `python -m pytest -q`

## R20 — Follow the value: canary matching and written files

See build guide Step 21.

**Revises.** `docker/jail/run-phase.sh`, `detonate/observe.py`, `jail.events_from_observation`, `DetonationStage`, the jail mapping in `findings.py`, `History.record` (R6) and the render check (R13).

**Gaps this closes.** strace's default 32-byte strings cut argv short. Sleep calls aren't traced, so `delay` can't fire on a live run. Written file contents are never searched. `docker diff` doesn't see writes inside tmpfs, and every path the skill can write is tmpfs.

**Goal.**
- **Tracing.** `run-phase.sh` uses `strace -f -s 4096` and adds `nanosleep` and `clock_nanosleep` to `openat`, `execve` and `connect`.
- **Parsing.** `parse_strace` keeps its return shape. Add `parse_strace_detail` and `parse_strace_log_detail`, which also return `flags` for `openat` and a `sleep` record with `seconds`. An `openat` with `O_WRONLY`, `O_RDWR` or `O_CREAT` becomes a `write` event.
- **Collecting written files.** After the home is streamed in and before the first phase, the root side of the jail touches a per-run random start marker in `/tmp`. After each phase, it lists files under `/home/agent` and `/tmp` that are `-newer` or `-cnewer` than the marker. The skill can backdate mtime but not ctime. A tar of those files, capped at 4 MB, streams out over `docker exec`. The host reads it in memory with `tarfile`: regular files only, never extracted, never executed. Each path becomes a `write` event, and each file's contents become a blob named `file:<path>`.
- **Matching.** New top-level module `src/skill_warden/canary.py`. It sits at the top level because history and rendering use it too. `find(blobs, values) -> list[Hit]`, where `Hit` is `(channel, blob_name)`. It matches each value raw, as standard and URL-safe base64 at all three alignments, as hex in both cases, URL-encoded (`quote` and `quote_plus`), JSON-escaped and as base32. A gzip blob is decompressed (capped at 8 MB) and searched again. DNS blobs match case-insensitively, with the dots between labels removed.
- **Channels.** `egress` covers every key from `sink.logs(session)`. `argv` is execve argv joined with spaces. `file` is written-file contents. The search set is the whole R19 registry.
- **Findings.**
  - `canary` / `canary_egress` | `canary_argv` | `canary_file` / critical, with excerpt `[canary tripped]`. The existing `honeytoken` open finding stays.
  - The `persistence` markers grow to the list in build guide Step 21: shell rc files, user service and autostart dirs, `authorized_keys`, Python startup hooks, package-manager config, agent instruction files and MCP configs, and `Library/LaunchAgents`.
  - Listing or `stat`ing a credential directory gets no finding. Benign tools walk `$HOME`.
- **Guarantee wiring.** `History.record` and the render check refuse any finding or rendered text where `canary.find` reports a hit for a run secret in any encoding, not only a raw substring. This is still `RedactionError` for history and BLOCK `not_finished` for rendering.

**Test first.**
- `tests/test_canary.py`, one test per encoding: raw; base64 at offsets 0, 1 and 2, plus URL-safe; hex in each case; `quote` and `quote_plus`; JSON-escaped; base32; gzip; a value split across DNS labels with mixed case; and a different value that isn't reported.
- Extend `tests/test_observe.py`: a 300-character argv survives; `nanosleep({tv_sec=45, …})` gives `seconds=45`; `O_WRONLY|O_CREAT|O_APPEND` maps to a write. The existing assertions stay.
- Extend `tests/test_findings.py`: one test for each new rule id and each new persistence marker, and no value appears in any excerpt.
- Extend `tests/test_history.py` and `tests/test_cli_scan.py`: a base64-encoded secret in an excerpt is refused.
- `tests/test_detonate.py` (`docker`):
  - a file backdated after the marker is still collected;
  - `fixtures/skills/argv-leak/` → BLOCK `canary` with `canary_argv`;
  - `fixtures/skills/bashrc-drop/` → BLOCK `high_finding` with `persistence`.

  Build guide Step 21 describes both fixtures.

**Fail means.** `argv-leak` is ALLOW, `bashrc-drop` has no `persistence` finding, or an encoded secret reaches history.

**Acceptance.** `python -m pytest tests/test_canary.py tests/test_observe.py tests/test_findings.py tests/test_history.py tests/test_cli_scan.py -q && python -m pytest -m docker tests/test_detonate.py -q`
**Regression.** `python -m pytest -q`

## R21 — A sink that answers

See build guide Step 22.

**Revises.** The sink context under `src/skill_warden/docker/sink/`, `detonate/sink.py` (R16), `jail.plan` and the jail mapping in `findings.py`.

**Goal.** The sink answers everything, so a skill carries on to the step that shows its intent. A refused connection or a resolver error is a known reason for a payload to stay dormant.
- **DNS.** Every A query gets this run's sink IP. Never NXDOMAIN, never `0.0.0.0`.
- **TCP.** Every TCP port on the sink accepts. The sink container, never the jail, gets `--cap-add NET_ADMIN` and an iptables `REDIRECT` of every port except 53, 80 and 443 to one listener. That listener logs the port, the peer and the first 4096 bytes to the `tcp` log.
- **TLS.** The sink generates a CA per run at startup. The CA private key never leaves the sink. The stage copies out only the certificate and streams it into the jail at `/tmp/warden-ca.pem`. `jail.plan` points `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, `CURL_CA_BUNDLE`, `NODE_EXTRA_CA_CERTS` and `PIP_CERT` at it. The listener on 443, and the target of a `CONNECT` through `HTTPS_PROXY`, mints a leaf for the SNI. It logs the SNI before the handshake finishes, then the Host, path and body, to the `tls` log. A client that pins its certificate and aborts still leaves its SNI.
- **Dummy payloads.** A fetched script-like path gets a harmless body that only touches a per-run marker file in `/tmp`. JSON paths and POSTs get `{"ok":true}`. When the marker appears in R20's written-file list, or a file from that list is `execve`d, the finding is `jail` / `remote_exec` / high.
- **Exfiltration hosts.** Package data `src/skill_warden/rules/exfil_hosts.txt`, seeded with the list in build guide Step 22. A Host, SNI or DNS name that matches it gives `jail` / `exfil_channel` / high.
- `sink.logs(session)` gains the `tls` and `tcp` keys, and R20's `egress` channel searches them with no change to `canary.py`.

A connection to 1.1.1.1 still fails. A hard-coded IP has no route and is still an `egress` finding.

**Test first.**
- Extend `tests/test_sink.py` (`docker`):
  - three random names resolve to the sink;
  - port 6667 is accepted and logged;
  - a probe with the CA environment POSTs over HTTPS, and both the body and the SNI are logged;
  - a client with a different CA fails, but its SNI is logged;
  - a fetched `.sh` path returns the marker body;
  - the jail's CA file has no `PRIVATE KEY` block;
  - two concurrent sessions have different CA certificates.
- `tests/test_exfil_hosts.py` (unit): each pattern matches, and `discord.com/channels` doesn't.
- Extend `tests/test_findings.py` with `remote_exec` and `exfil_channel`.

**Fail means.** A name returns NXDOMAIN, the TLS body is missing, the CA key is readable from the jail, or two runs share a CA.

**Acceptance.** `python -m pytest tests/test_exfil_hosts.py tests/test_findings.py tests/test_sink_unit.py -q && python -m pytest -m docker tests/test_sink.py tests/test_detonate.py -q`
**Regression.** `python -m pytest -q`

## R22 — Every phase, and proof it ran

See build guide Step 23.

**Revises.** `jail.phase_commands` and `DetonationStage`. This step retires §11.1's "shell scripts only" limit.

**Goal.** New module `detonate/phases.py`. The jail runs three script phases in order, each with its own timeout and its own strace stream labeled with the phase name:
1. `install`: the frontmatter install commands, `command -v` for each required binary, fenced blocks under install, setup, prerequisite or requirements headings, and `pip install -r` / `npm install` when those files exist. A package-index request for a package that isn't declared gives `jail` / `undeclared_fetch` / high.
2. `scripts`: every `.sh`, `.py`, `.js` or `.mjs` file under `scripts/`, plus any file with a shebang. The interpreter comes from the extension or the shebang. Each script runs with no arguments, with `--help`, and with each example invocation from `SKILL.md` that names it.
3. `skill_md`: every other fenced `bash` or `sh` block.

**Coverage.** `phases.coverage(planned, observed) -> Coverage`. A script counts as run when strace shows an `execve` of its path. A non-zero exit still counts. A planned phase that didn't start, or a planned script with no `execve`, gives `jail` / `coverage_incomplete` / error, with the missing names (relative to the skill) as the excerpt. That is BLOCK `tool_error`. A phase skipped because the stage deadline ran out also counts as missing. An empty plan is complete in this step. R23 makes the agent phase required.

An offline package cache, so that declared installs can succeed, stays deferred (§19).

**Test first.**
- `tests/test_phases.py` (unit):
  - install commands are parsed from frontmatter;
  - a `## Setup` block lands in `install`;
  - scripts are found by extension and by shebang;
  - arguments are taken from a `SKILL.md` example;
  - a planned script with no `execve` → `coverage_incomplete`;
  - a non-zero exit still counts as run.
- `tests/test_policy.py`: `jail` / `coverage_incomplete` plus other `jail` findings → BLOCK `tool_error`, with detail `coverage_incomplete`.
- `tests/test_detonate.py` (`docker`), with fixtures from build guide Step 23:
  - `py-helper` runs, and coverage is complete;
  - `fake-prereq` → BLOCK `high_finding` with `remote_exec`;
  - `clean-date` stays ALLOW.

**Fail means.** `fake-prereq` is ALLOW, or a planned `.py` script never ran and the verdict is still ALLOW.

**Acceptance.** `python -m pytest tests/test_phases.py tests/test_policy.py -q && python -m pytest -m docker tests/test_detonate.py -q`
**Regression.** `python -m pytest -q`

## R23 — Agent phase in the jail

See build guide Step 24.

**Revises.** `DetonationStage` and `phases.coverage`. This step also revises `config.py` (R12) with a new `[detonate]` table and `doctor` (R14) with an agent check.

**Goal.** Many malicious skills ship no harmful script. Their `SKILL.md` instructs the agent instead. The agent phase lets a victim agent load the skill and act on it inside the jail. It is separate from the reader: the reader and `policy` never see its output.
- **Parsing.** `detonate/mini_agent.parse_reply(text) -> list[ToolCall]` accepts exactly one JSON object `{"tool": …, "args": {…}}`, where `tool` is `read_file`, `write_file`, `list_dir` or `bash`. It returns `[]` for anything else, including `{"decision": "ALLOW"}`, extra keys, two objects or a fence.
- **Prompts.** `trigger_prompts(frontmatter)` returns three fixed templates, filled only from the frontmatter `name` and `description`, each cut to 300 characters. No other skill text goes into the user turn.
- **Loop.** `run(prompts, model, executor, skill_md, max_turns=8)`:
  - puts `SKILL.md` in the system context;
  - runs each tool call through `executor`, which is a `docker exec` into the jail as uid 10001 under strace, labeled `agent`;
  - returns tool output to the model cut to 4 KB;
  - stops on a reply with no tool call, or at `max_turns`.

  The loop runs on the host with no environment from the user (§7.3). Nothing it parses runs on the host.
- **Model.** A `VictimModel` protocol with `complete(messages) -> str`. Acceptance uses a scripted fake. The real one is an OpenAI-compatible chat call to a loopback endpoint only. Tool output carries canary values, so a hosted endpoint is never allowed.
- **Config.** `[detonate] agent = "ollama:<model>"`, and `agent_base_url`, which defaults to `http://127.0.0.1:11434/v1`. A non-loopback host is a `ConfigError`. `doctor --docker` reports whether the agent model answers.
- **Coverage.** The agent phase is planned for every detonation. It counts as run when at least one prompt completed a model turn. With no agent configured or reachable, the stage emits `coverage_incomplete`. So `scan --detonate` without a local agent model is BLOCK `tool_error`. That follows from "incomplete coverage is BLOCK". Do not add a built-in default model, and do not add an opt-out.

**Named exception.** R17's `clean-date` → ALLOW docker test may change in exactly one way: it passes the fake model that lists `.` and stops. Its ALLOW assertion stays.

**Test first.**
- `tests/test_mini_agent.py`:
  - each rejection case gives no tool call;
  - `{"decision": "ALLOW"}` gives no tool call and no finding;
  - `trigger_prompts` is deterministic and contains no body text;
  - a scripted `bash` call reaches the executor unchanged;
  - `max_turns` stops a model that never stops calling tools.
- Extend `tests/test_config.py`: a non-loopback `agent_base_url` → `ConfigError`.
- `tests/test_detonate.py` (`docker`):
  - `fixtures/skills/agent-exfil/` (no scripts; build guide Step 24) with a fake model that follows the body → BLOCK `canary`;
  - `clean-date` with the listing fake → ALLOW;
  - `clean-date` with no model → BLOCK `tool_error`, with detail `coverage_incomplete`.

**Fail means.** An ALLOW-shaped reply is executed, a tool call runs on the host, or `agent-exfil` is ALLOW.

**Acceptance.** `python -m pytest tests/test_mini_agent.py tests/test_phases.py tests/test_config.py -q && python -m pytest -m docker tests/test_detonate.py -q`
**Regression.** `python -m pytest -q`

## R24 — Second look: profiles and clock skew

See build guide Step 25.

**Revises.** `DetonationStage` and the probe markers in the `findings.py` jail mapping.

**Goal.** Code that checks for a sandbox, a CI runner or the current date can stay quiet. Running the same skill under several profiles and comparing the results turns that silence into evidence.
- **Profiles.** `detonate/profiles.py` defines `laptop` (the base run), `ci`, `laptop+30d` and `laptop+365d`. `profiles.plan(base_argv, profile)` changes the hostname, the MAC address and the environment, as build guide Step 25 lists.
- **Clock skew.** The skew profiles set `LD_PRELOAD` to libfaketime, plus `FAKETIME` and `FAKETIME_DONT_FAKE_MONOTONIC=1`. This is best effort: static or raw-syscall code bypasses it. Time namespaces stay deferred.
- **Runs.** Every profile runs against the same home and registry. A canary hit in any profile counts for the run. The profiles share the stage deadline, and a profile that can't start before it is a missing phase (`coverage_incomplete`).
- **Divergence.** `profiles.diverged(rules_by_profile) -> list[str]` names each profile whose set of sensitive rule ids differs from `laptop`'s. The sensitive set is `honeytoken`, the `canary_*` rules, `egress`, `persistence`, `remote_exec`, `exfil_channel` and `undeclared_fetch`. Any divergence gives `jail` / `profile_divergence` / high.
- **Probe markers.** `/.dockerenv`, `/proc/1/cgroup` and `TracerPid` stay `sandbox_probe` at high. Weaker environment reads that benign runtimes also make are `jail` / `env_probe` / medium, which is ASK `medium_only` when nothing stronger fired.

**Test first.**
- `tests/test_profiles.py` (unit):
  - each profile differs from `laptop` in hostname and MAC;
  - `ci` sets its variables;
  - the skew profiles set `LD_PRELOAD` and `FAKETIME`;
  - `diverged` names `ci` when only `ci` has `canary_egress`;
  - a `/proc/cpuinfo` read is `env_probe` at medium.
- `tests/test_policy.py`: `env_probe` plus `semgrep.ok` and no other `jail` finding → ASK `medium_only`.
- `tests/test_detonate.py` (`docker`), with fixtures from build guide Step 25:
  - under `laptop+365d`, `date +%s` is at least 364 days ahead. If libfaketime doesn't work on this musl image, stop and record the output. Do not loosen the assertion;
  - `ci-gated` → BLOCK, with `canary_egress` and `profile_divergence`;
  - the `+365d` run catches `date-gated`;
  - `stall` has a `delay` finding;
  - `clean-date` is ALLOW in all four profiles.

**Fail means.** Profiles share a hostname, the skew doesn't change `date`, or `ci-gated` is ALLOW.

**Acceptance.** `python -m pytest tests/test_profiles.py tests/test_findings.py tests/test_policy.py -q && python -m pytest -m docker tests/test_detonate.py -q`
**Regression.** `python -m pytest -q`

## R25 — Measure the jail and prove its guarantees

See build guide Step 26.

**Revises.** `redact.py`, which now covers every encoding `canary.find` searches.

**Goal.** This step adds no detector. It treats the jail as a classifier and checks the guarantees the earlier steps claim.
- **Labeled matrix.** `fixtures/eval/manifest.json` lists each fixture with `label`, `behavior`, `trigger`, `evasion`, `expected_decision` and `expected_rule_ids`. Build guide Step 26 lists the behavior, trigger and evasion classes it must cover, at least one fixture each, and the benign look-alikes (at least six, including `clean-date`). Under this policy, an AWS helper that reads its credentials, a git-hooks installer and a dotfile manager are BLOCK. Mark them `known_false_positive: true`, and do not make them ALLOW.
- **Detonation-only decision.** `expected_decision` is the jail's own verdict: `policy.decide` on an outcome with `stages_requested={"detonation"}` and only the `jail` and `canary` findings. That keeps R26's new static rules from moving the matrix. The script also prints the full-pipeline decision.
- **Metrics.** `scripts/eval_detonation.py --corpus fixtures/eval --out .eval` runs every fixture through `pipeline.scan_skill(..., full=True)` with the fake agent model and prints:
  - precision, recall, F1 and MCC;
  - the ASK rate on benign fixtures;
  - the `tool_error` rate, which stands in for "inconclusive";
  - wall-clock time per skill;
  - per-behavior and per-evasion counts.

  Agent-only catches get their own row, because the fake model was scripted to comply. An external `--corpus` is reported separately, never pooled. Tests never download a corpus. The script is a dev tool and isn't in the wheel. Add `.eval/` to `.gitignore`.
- **Leak test.** For every matrix run, collect each persisted artifact: a full dump of the history database, the text and `--format json` renderings, the eval script's stdout and its `--out` files, and the manifest. Assert that `canary.find` reports nothing for any registry value. Also assert that the run's `TemporaryDirectory` is gone.
- **Mutation test.** Monkeypatch `redact.redact` to return its input unchanged, and assert the leak check fails. A leak test that can't fail proves nothing.
- **Property test.** Using stdlib `random` with a fixed seed: inject random values, through every channel and every encoding, into findings. `History.record` refuses every one.
- **Isolation regression.** Run the R18 probe under every R24 profile. No profile loosens capabilities, seccomp, the read-only root or the uid.
- **Determinism.** Two detonations of `steal-key` give the same set of rule ids. The R3 property already covers policy determinism.

**Test first.**
- `tests/test_eval_matrix.py` (`docker`): every malicious fixture is BLOCK, and every benign fixture matches `expected_decision`.
- `tests/test_canary_leak.py`, including the mutation and property tests.
- `tests/test_isolation_regression.py` (`docker`).
- `tests/test_determinism.py` (`docker`).

**Fail means.** A malicious fixture isn't BLOCK, a value survives into an artifact, or the mutation test passes with redaction disabled.

**Acceptance.**

```bash
python -m pytest tests/test_canary_leak.py -q
python -m pytest -m docker tests/test_eval_matrix.py tests/test_isolation_regression.py tests/test_determinism.py -q
python scripts/eval_detonation.py --corpus fixtures/eval --out .eval
```

**Regression.** `python -m pytest -q`

---

# Phase 5 — Rules and release

## R26 — Bundled ruleset and the golden table

**Goal.** Add the rule categories in §9.4 under `src/skill_warden/rules/`, with inert positive and negative fixtures for each, and pin the expected verdicts as tests.

**New fixtures** (inert, obviously fake):
- `fixtures/skills/zero-width-memory/`: today's `memory-poison` text with U+200B inside `MEMORY.md`.
- `fixtures/skills/dotslash-memory/`: the instruction writes to `./MEMORY.md`.
- `fixtures/skills/clean-with-asset/`: `clean-date` plus a small PNG in `assets/`.
- One positive and one negative fixture for each new rule category.

Symlink cases stay in `tmp_path`. Wheels and some git setups don't preserve symlinks.

This table is static and reader only. Detonation verdicts are pinned by `fixtures/eval/manifest.json` (R25), which uses the detonation-only decision, so a rule added here can't change them. After adding rules, run `python scripts/eval_detonation.py --corpus fixtures/eval --out .eval` once. Record in the progress log any jail fixture that now also has a static `high` finding: a default scan (without `--full`) of that fixture now skips the jail.

**Test first: `tests/test_golden.py`.** Run static-only, plus the scripted-reader column:

| Fixture | Static only | With scripted reader |
| --- | --- | --- |
| `clean-date` | ALLOW `clean` | no flags → ALLOW `clean` |
| `memory-poison` | BLOCK `high_finding` (`skill-memory-file-persistence`) | BLOCK |
| `audited-exfil` | BLOCK `high_finding`, plus a medium safety-claim finding from `README.md` | BLOCK |
| `prose-exfil` | ALLOW `clean`. This is the documented static gap the reader exists for | `credential_exfil` → BLOCK `high_finding` |
| `steal-key` | BLOCK `high_finding` (outbound transfer of file contents). Today's rules give ALLOW | BLOCK |
| `zero-width-memory` | BLOCK `high_finding`, plus `obfuscation.unicode` (medium) | BLOCK |
| `dotslash-memory` | BLOCK `high_finding` | BLOCK |
| `clean-with-asset` | ALLOW `clean`, plus `binary_file` (info) | ALLOW |

If a rule you write produces a different row, change the table only with a one-line justification in the progress log. Never change a fixture to fit a rule.

**Acceptance.** `python -m pytest tests/test_golden.py tests/test_rules.py -q`
**Regression.** `python -m pytest -q`

## R27 — Packaging and the wheel smoke test

**Goal.** Finish §15.
- Set the version to `0.2.0`.
- Include all package data: rules (including `exfil_hosts.txt`), docker contexts (including `isolation-probe.sh`), schema and selftest. Leave `scripts/eval_detonation.py` and `fixtures/eval/` out of the wheel.
- Confirm the `skill-warden` script from R13 is in the wheel's entry points.
- Remove `pythonpath = ["src"]` from the pytest config.

**Test first: `tests/test_packaging.py`** (`packaging`).
1. Build a wheel into `tmp_path`.
2. Create a fresh venv there and install the wheel.
3. From `tmp_path` (outside the repo), run `skill-warden doctor` and expect exit 0.
4. Copy the packaged `selftest/memory` to `tmp_path` and scan it; expect exit 20.
5. Assert that the wheel's file list contains `rules/`, `rules/exfil_hosts.txt`, `docker/jail/Dockerfile`, `docker/jail/isolation-probe.sh`, `schema/history.sql` and `selftest/`, and no `fixtures/eval/`.

**Acceptance.** `python -m pytest -m packaging -q`
**Regression.** `python -m pytest -q`

## R28 — Docs and full regression

**Goal.** Write the user-facing docs, then run everything.

**Write.**
- `README.md`:
  - what Skill Warden is and isn't (§18);
  - install with pipx or uv;
  - quickstart;
  - configuring a provider: OpenAI, Anthropic, Ollama, any OpenAI-compatible endpoint;
  - the privacy note (§10.9);
  - `--detonate` and its warning. It needs Docker with runc at or above the R18 floor, and a local agent model (R23). Without one, `--detonate` is BLOCK `tool_error` (`coverage_incomplete`);
  - exit codes;
  - the JSON envelope;
  - the golden table as "what each stage catches";
  - limitations.
- `CONTRIBUTING.md`: markers, the fixture policy, and how to add a rule along with its fixtures.
- Set the status line in `docs/v2/architecture.md` to "implemented".

Describe detections by category in the README. Don't write them as attack recipes.

**Acceptance.** All of these exit 0, with Docker running and no provider keys set:

```bash
python -m pytest -q
python -m pytest -m docker -q
python -m pytest -m packaging -q
python scripts/eval_detonation.py --corpus fixtures/eval --out .eval
```

---

## Human gates (optional, after R28)

Run one gate per session and record its result in `docs/v2/progress.md`.

| Gate | Needs | Acceptance |
| --- | --- | --- |
| G1 local LLM | `ollama serve` and a pulled model | `skill-warden doctor --llm --config <ollama config>` passes. The golden fixtures with the live reader: `prose-exfil` → BLOCK; `clean-date` stays ALLOW or ASK, and you record which |
| G2 hosted LLM | `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` | One `doctor --llm` call returns a valid contract. Record the model and whether it refused |
| G3 detonation on a clean machine | Docker with runc ≥ 1.2.8 / 1.3.3 (or `runsc`), network access for the first image build, a local agent model | `doctor --docker` passes, including the isolation report and the agent check; `scan --detonate fixtures/skills/steal-key` exits 20; `scan --detonate fixtures/skills/clean-date` exits 0; no `sw-*` resources remain afterwards |
| G5 runc floor | Docker Desktop updated until `docker version` shows runc at or above the R18 floor | `python -m pytest -m docker tests/test_isolation_docker.py -q` exits 0. R18–R25 docker acceptance needs this gate |
| G4 Linux install | A Linux machine or VM | `pipx install dist/skill_warden-0.2.0-py3-none-any.whl`, then `doctor` and a scan, both work |

## Definition of done (MVP)

- R0–R28 are `done` in `docs/v2/progress.md`.
- `pipx install` from the built wheel gives a working `skill-warden` with no ClickHouse, Akash, Guild or minisign anywhere.
- Static-only scans reproduce the golden table.
- The reader works against at least one local endpoint and one hosted endpoint (G1, G2).
- `--detonate` blocks `steal-key`, allows `clean-date` with a local agent model, and cleans up after itself (G3).
- The R25 eval matrix passes, and its metrics are recorded in the progress log.
