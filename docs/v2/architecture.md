# Skill Warden v2 — architecture of the downloadable MVP

Status: **target design. No code has changed yet.** `docs/v2/refactor-guide.md` moves the current code to this design one tested step at a time, and `docs/v2/progress.md` tracks the steps.

This document replaces `docs/architecture.md` (the hackathon build, kept as a record) for everything except `demo/`, which is out of scope and left as it is. Facts were checked on 14 October 2026. §20 lists what was verified and how.

---

## 1. Product

Skill Warden is a local, fail-closed gate for third-party agent skills. A skill is a directory built around a `SKILL.md`, the format that Claude Code, Pi, OpenClaw and other agents load. A developer runs Skill Warden before installing a skill, or in CI against a repository's `.claude/skills/`:

```text
$ skill-warden scan ./downloads/date-helper
BLOCK  date-helper   reason: high_finding (skill-memory-file-persistence)
  severity  source   rule                            location
  high      semgrep  skill-memory-file-persistence   SKILL.md:8
  medium    reader   false_safety_claim              -
coverage   static ok   reader ok (ollama:qwen2.5:7b)   detonation not requested
```

Three properties define the product:

1. **Local by default.** It needs no account, cloud service or API key. Nothing leaves the machine unless the developer configures a hosted LLM.
2. **Fail-closed.** If a stage times out, crashes, returns something that can't be parsed, or silently does nothing, the result is BLOCK, and the reason names the stage.
3. **Evidence over claims.** A skill's README, frontmatter or marketplace badge never counts toward safety. A deterministic policy picks BLOCK, ASK or ALLOW. A model never does.

---

## 2. Decisions

| Question | v2 | Hackathon build |
| --- | --- | --- |
| What ships? | A Python CLI: `pipx install skill-warden` | A demo pipeline driven by one Python process |
| Who picks BLOCK, ASK or ALLOW? | `policy.decide()`, a pure function over findings | One ClickHouse SQL statement |
| Where is history kept? | A SQLite file in the user's data directory (stdlib `sqlite3`) | ClickHouse Cloud, or ClickHouse in Docker |
| Static analysis | Semgrep CLI as a declared dependency, with bundled rules, fail-closed | The same tool, fail-open when Semgrep errors |
| LLM reader | Opt-in. Any OpenAI-compatible endpoint (hosted or local) or Anthropic | AkashML only |
| Running the skill | Opt-in `--detonate`, local Docker jail | The same jail, with a hard-coded network and images rebuilt on every run |
| Publishing verdicts | Exit codes and JSON. The user's CI decides what to do with them | Guild agent → GitHub PR → Akash page (never built) |
| Signing | Deferred. History is hash-chained | minisign (never built) |
| Cost controls | Size caps, timeouts, one LLM call per skill | A USD budget breaker for Akash and AkashML |

Semgrep remains a required dependency. Today the bundled rule set is one regex (`languages: [generic]`), so the engine does little that Python's `re` couldn't. Semgrep stays for three reasons:

- It gives rules a format people can review.
- Users who want them can add registry rule packs.
- It can do language-aware matching on the Python and shell files that skills ship in `scripts/` (§9.4).

The cost is install size. `pipx` or `uv tool` keep that out of the user's own environments.

---

## 3. What goes, what stays

### 3.1 Removed

| Removed | Why it existed | Why it goes | Replacement |
| --- | --- | --- | --- |
| ClickHouse: Cloud, the local container, `clickhouse-connect`, `schema/*.sql` | Sponsor integration; the verdict SQL | It's a server process and a paid trial for a single-user CLI, and the tests needed Docker | `policy.py`, plus `history.py` on SQLite |
| AkashML | Sponsor integration; the reader backend | Paid, single provider | A provider-agnostic reader (§10) |
| Akash verdict page, Guild publisher, GitHub pin PRs | Sponsor demo path | Hosted control planes paid for with credits. Never built | JSON report and exit codes. A CI integration is on the roadmap |
| minisign | Signing the verdict file in the PR | An extra binary that only matters once verdicts are published | Hash-chained history. Signing is on the roadmap |
| `breaker.py` | Capping Akash escrow and AkashML spend | No metered backend is used by default | Size caps, timeouts and a single call per skill (§14) |
| `memory.py` (fleet memory) | Narrative for the memory-poisoning demo | It never fed the verdict | Roadmap: approvals bound to a content hash (§19) |
| `registry.py` and its `publisher/name/version` layout | The local demo registry | Real skills live in `~/.claude/skills/<name>/` and similar places | `intake.discover()` |
| `orchestrator.py`, and `detonate()` writing to the store itself | Two parallel pipelines | They drifted apart (§17.1 #13) | One `pipeline.py` |
| Pi integration | The unsandboxed victim in the attack demo | A scanner doesn't need it | The honeytoken home still plants agent-config decoys |
| `scripts/try_sample_skill.py` | ClickHouse walkthrough | Depends on ClickHouse | `skill-warden scan fixtures/…` |

`scripts/export_demo_traces.py` imports ClickHouse, so it stops working once ClickHouse is removed. `demo/` reads the committed `demo/src/data/traces.json`, so the deck keeps building. Deleting or porting the export script is a separate decision.

### 3.2 Kept

- Semgrep.
- The `content_hash` algorithm. It is unchanged, so hashes stay comparable with the hackathon runs.
- `redact` and `excerpt`.
- The finding-mapping tables.
- Honeytokens and the nonce search.
- strace and diff parsing.
- The jail's hardening flags and `pack_skill`.
- The sink's DNS and HTTP catch-all.
- The fixtures.
- The fail-closed decision table, ported in §12.

### 3.3 Dependencies

| | Hackathon | v2 core | v2 optional |
| --- | --- | --- | --- |
| Python packages | `clickhouse-connect`, `httpx`. `semgrep` was used but not declared | `httpx`, `semgrep` | `anthropic`, as the extra `skill-warden[anthropic]` |
| Services | ClickHouse Cloud, AkashML, Akash Console, Guild, GitHub | none | A hosted LLM API, if the user picks one |
| Local tools | Docker (required by tests), minisign, Node (verdict page) | none | Docker (for detonation); Ollama, LM Studio or vLLM (for a local LLM) |
| Default cost | ClickHouse trial, Akash and AkashML credits | $0 | Whatever the chosen LLM provider bills |

---

## 4. Principles

1. **The judge and the subject stay apart.** Skill text never enters the prompt of a process that holds tools or credentials. The reader model has no tools, and its output is parsed as data.
2. **Fail closed.** A missing, partial or unparseable stage result is BLOCK. The reason says which stage failed and why.
3. **Evidence only accumulates.** Every stage can add findings. No stage can remove or downgrade another stage's finding. A reader that is talked into returning no flags can't produce ALLOW; it only fails to add evidence.
4. **Local by default.** Semgrep runs with metrics off and the version check disabled. Detonation networks are internal-only. Network use happens only when the user chooses a hosted LLM or Semgrep registry rules.
5. **Say what ran.** Every report lists the stages that ran. An ALLOW from static checks alone is labeled "static only."
6. **The scanned thing never configures the scanner.** Config, rules and ignore files are never read from the skill or from the directory being scanned.

---

## 5. System overview

```text
skill-warden scan PATH...
        |
        v
+----------------+  symlink, too large, unreadable  -> error findings
|  Intake        |  content_sha256 over the original bytes
|  discover,     |  normalized copy (NFKC, Unicode Cf stripped) -> obfuscation finding
|  inventory     |
+-------+--------+
        | normalized text files
        v
+----------------+  always
|  Static        |  semgrep subprocess, bundled rules, liveness canary
+-------+--------+
        v
+----------------+  opt-in: --llm, or an [llm] table in config
|  Reader        |  OpenAI-compatible (httpx) | Anthropic (official SDK extra)
+-------+--------+  no tools, flags-only JSON, prompt canary
        v
+----------------+  opt-in: --detonate, needs Docker
|  Detonation    |  per-run internal network + sink + hardened jail + honeytokens
+-------+--------+
        v
   findings[] --> policy.decide() --> Verdict --> report (text or JSON) + exit code
                                          \--> history.sqlite3 (hash chain)
```

| Stage | Runs | Needs | Adds |
| --- | --- | --- | --- |
| Intake | always | nothing | integrity findings, the content hash, the normalized copy |
| Static | always | `semgrep`, installed with the package | rule matches, `semgrep.ok` |
| Reader | `--llm` or `[llm]` in config | an OpenAI-compatible endpoint, or an Anthropic key | flags, `reader.ok` |
| Detonation | `--detonate` | Docker | behavior findings, honeytoken trips, `jail.ok` |
| Policy | always | nothing | the verdict |

Trust boundaries:

```text
+----------------------- host process (trusted) ------------------------+
| config | bundled rules | policy | history.sqlite3 | API key (from env) |
|                                                                        |
|  intake -> semgrep subprocess        reader client -> LLM endpoint     |
|  (skill bytes read as data)          (skill text out; response parsed |
|                                       as untrusted data)              |
|  detonation controller -> docker CLI                                   |
+-----------------------------------+------------------------------------+
                                    |  no mounts, no host env, no docker.sock
+------------------- per-run internal network (untrusted) --------------+
|  jail: the skill's scripts + honeytoken home, run as uid 10001        |
|  sink: answers every DNS name + HTTP catch-all (trusted observer)     |
+-------------------------------------------------------------------------+
```

---

## 6. CLI contract

### 6.1 Commands

| Command | Purpose |
| --- | --- |
| `skill-warden scan PATH... [options]` | Scan one or more skills |
| `skill-warden scan --installed` | Scan the configured skill roots. Defaults: `~/.claude/skills`, `./.claude/skills` |
| `skill-warden init` | Write a commented config template. It never asks for or stores a key |
| `skill-warden doctor [--llm] [--docker]` | Self-test (§6.5) |
| `skill-warden history [--limit N] [--verify]` | List past verdicts. `--verify` re-checks the hash chain |
| `skill-warden show RUN_ID` | Print a stored report |

Scan options:

- `--llm PROVIDER:MODEL` or `--no-llm`. The split is on the first colon, so `ollama:qwen2.5:7b` works.
- `--detonate`
- `--full`: run every requested stage even after a BLOCK is certain (§7.2).
- `--format text|json` and `--out FILE`
- `--config FILE`
- `--rules DIR` (repeatable): extra local Semgrep rules.
- `--no-history`
- `--timeout SECONDS`

### 6.2 Discovery

`PATH` can be any of three things:

- a skill directory (one that contains `SKILL.md`);
- a `SKILL.md` file, in which case its parent directory is the skill;
- a root to search.

Searching works like this:

- The search walks at most four levels deep and doesn't follow symlinks.
- On each branch, the first directory that contains `SKILL.md` is one skill. Everything under it belongs to that skill, including any nested `SKILL.md`.
- If no skills are found, the CLI exits with code 2.
- If the root itself is a symlink (common for skills linked into `~/.claude/skills`), it is resolved once and recorded as an `info` finding.
- Any symlink inside a skill is an error (§8).

### 6.3 Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Every scanned skill is ALLOW |
| 10 | The worst verdict is ASK |
| 20 | The worst verdict is BLOCK |
| 2 | Usage or configuration error. Nothing was scanned |
| 1 | Unexpected internal error |

CI should treat any non-zero code as "not allowed." The verdict codes are spaced so they never collide with argparse's 2 or with Python's 1 for an uncaught exception.

An exception inside one skill's scan is caught by the pipeline. That skill is reported as BLOCK `not_finished` and the other skills are still scanned (§7.3).

### 6.4 Output

The text format is for people. The JSON format is for machines; `--out` always writes JSON. One envelope is used, whether one skill or several were scanned:

```json
{
  "schema": "skill-warden/scan@1",
  "tool": {"name": "skill-warden", "version": "0.2.0", "semgrep": "1.180.0", "rules_sha256": "…"},
  "summary": {"skills": 1, "worst": "BLOCK", "counts": {"BLOCK": 1, "ASK": 0, "ALLOW": 0}},
  "reports": [
    {
      "run_id": "5b1e…",
      "skill": {"path": "/abs/path", "name": "date-helper", "content_sha256": "…"},
      "coverage": {
        "static": {"status": "ok"},
        "reader": {"status": "off"},
        "detonation": {"status": "not_requested"}
      },
      "verdict": {"decision": "BLOCK", "reason": "high_finding", "detail": "skill-memory-file-persistence"},
      "findings": [
        {"source": "semgrep", "rule_id": "skill-memory-file-persistence", "severity": "high",
         "file": "SKILL.md", "line": 8, "excerpt": "Instruction to write or append…", "evidence_hash": "…"}
      ],
      "timings_ms": {"intake": 4, "static": 2310}
    }
  ]
}
```

Excerpts are redacted (§7.4) and capped at 200 characters. Coverage status values are `ok`, `failed`, `timeout`, `skipped` (short-circuited or blocked by intake), `off` (not configured) and `not_requested`.

### 6.5 `doctor`

| Check | Default | How |
| --- | --- | --- |
| Semgrep found, and its version | yes | §9.1 resolution |
| Bundled rules load and detect | yes | Run the static stage on the packaged self-test skills: `selftest/clean` must be ALLOW and `selftest/memory` must be BLOCK `high_finding`. This proves the binary, the rules, the liveness canary and the parser end to end on this machine |
| Config parses and validates | yes | Strict schema. An unknown key is an error that names the key path |
| Reader contract | `--llm` | One request with `selftest/clean`, announced before it is sent because it may cost money. A valid response passes whatever flags it contains |
| Docker | `--docker` | Engine reachable; a throwaway `--internal` network with `gateway_mode_ipv4=isolated` can be created and removed; images are built and cached; `selftest/clean` detonates to `jail.ok` |
| Privacy | yes | Prints whether skill text would leave the machine: a hosted provider versus localhost |

---

## 7. Pipeline and data model

### 7.1 Types (`models.py`)

```python
class Severity(StrEnum):  INFO, LOW, MEDIUM, HIGH, CRITICAL, ERROR       # values "info" … "error"
class Source(StrEnum):    INTAKE, SEMGREP, READER, JAIL, CANARY
Stage = Literal["static", "reader", "detonation"]

@dataclass(frozen=True)
class Finding:
    source: Source; rule_id: str; severity: Severity
    file: str = ""; line: int | None = None; excerpt: str = ""
    # evidence_hash: sha256 of excerpt, computed (same as today's rows)

@dataclass(frozen=True)
class FileEntry:   relpath: str; size: int; kind: Literal["text", "binary"]; executable: bool
@dataclass(frozen=True)
class SkillRecord: path: Path; name: str; content_sha256: str | None; files: tuple[FileEntry, ...]
@dataclass(frozen=True)
class StageResult: stage: Stage; status: Literal["ok", "failed", "timeout", "skipped"]
                   findings: tuple[Finding, ...]; detail: str = ""; elapsed_ms: int = 0
@dataclass(frozen=True)
class RunOutcome:  run_id: UUID; status: Literal["completed", "timeout", "error"]
                   stages_requested: frozenset[Stage]; findings: tuple[Finding, ...]
@dataclass(frozen=True)
class Verdict:     decision: Literal["BLOCK", "ASK", "ALLOW"]; reason: str; detail: str
@dataclass(frozen=True)
class Report:      run_id; skill: SkillRecord; outcome: RunOutcome; verdict: Verdict
                   coverage: dict[Stage, StageResult]; timings_ms: dict[str, int]
```

`publisher` and `version` from the hackathon registry are no longer required fields. `name` comes from the frontmatter, falling back to the directory name.

### 7.2 Flow (`pipeline.scan_skill`)

1. **Intake** (§8) produces the `SkillRecord` and intake findings. If an intake finding has severity `error`, the static, reader and detonation stages are all `skipped`. The verdict is already BLOCK, so there's no point scanning a tree that failed intake, spending money, or running untrusted code.
2. **Static** (§9). It always runs unless intake failed.
3. **Reader** (§10), if requested.
4. **Detonation** (§11), if requested.
5. **Collect** the findings from every stage and redact them.
6. **Decide:** `policy.decide(RunOutcome)` (§12).
7. **Record** to history, unless `--no-history` was passed (§13).
8. **Return** the `Report`. The CLI renders it and folds its decision into the exit code.

**Short-circuit.** By default, once collected findings include a `canary`, any `error`, or any `high`/`critical` finding, the remaining stages are `skipped`. This is safe because those conditions are "any" checks in §12, and evidence only accumulates: no later finding can change the decision away from BLOCK. It also means a skill that is already blocked costs no LLM call and runs no untrusted code. `--full` turns short-circuiting off when a complete report is wanted.

**Timeouts.** There is a global per-skill wall clock (`scan.timeout_seconds`, default 300). Each stage gets whatever time remains. If the clock runs out, `RunOutcome.status` is `timeout`, which means BLOCK `timeout`. Running out of a single stage's own timeout is that stage's error finding instead.

### 7.3 Stage isolation

- Every stage function catches its own exceptions. It returns `StageResult(status="failed")` carrying an `error` finding whose `rule_id` names the failure.
- An exception that escapes a stage is a bug. The pipeline catches it and sets `RunOutcome.status = "error"`, which is BLOCK `not_finished`. It never crashes the CLI.

### 7.4 Redaction

Each run keeps a list of secrets:

- every honeytoken plant value, plus the nonce;
- the value of the configured API key, as defence in depth.

`redact()` runs before `excerpt()` cuts the text, as it does today. The history writer refuses any finding whose excerpt still contains a secret (`RedactionError`, which is today's `Store` check moved to the new store).

The same check runs before rendering. Text output, `--format json` and `--out` usually end up in CI logs, so a rendered report that would contain a run secret is an internal error. The run is reported as BLOCK `not_finished` and the secret is never printed.

---

## 8. Intake (`intake.py`)

1. **Inventory.** Walk the skill without following links.
   - A symlink anywhere inside the skill → `symlink` (error).
   - A device file or FIFO → `unreadable` (error).
2. **Caps.** These are configurable: at most 500 files, at most 5 MiB in total, and no single file over 1 MiB. Exceeding any cap gives `too_large` (error) and no further stages run.
3. **Identity.** `content_sha256 = hashing.content_hash(root)`. The algorithm is unchanged: length-prefixed relative POSIX path plus raw bytes, sorted by path, with a top-level file named `HASH` ignored. If intake raised an error, `content_sha256` is `None` and the verdict is already BLOCK.
4. **Classify each file** as text or binary.
   - If it decodes as UTF-8, it is text.
   - If it fails to decode but has a text extension (`.md`, `.txt`, `.sh`, `.py`, `.js`, `.ts`, `.json`, `.yaml`, `.yml`, `.toml`), that is `undecodable_text` (medium). An agent may still read it, and Warden can't.
   - A binary that has executable magic (ELF, Mach-O, PE, WASM), has the executable bit set, or sits under `scripts/` is `opaque_binary` (medium).
   - Any other binary (images, fonts) is `binary_file` (info).
5. **Normalize.** Copy the text files into a private temporary directory with mode 0700. NFKC-normalize them and strip Unicode format characters (category `Cf`: zero-width characters, bidi controls, a stray BOM).
   - If stripping removed any `Cf` character, record `obfuscation.unicode` (medium) against that file.
   - An NFKC-only change, such as a non-breaking space or a ligature, is not a finding. It is too common in ordinary documents. It still helps matching.
   - The static stage and the reader read only this copy. The content hash is computed over the original bytes.
6. **Frontmatter.** Read `name` and `description` with a small line parser. Don't add a YAML dependency. If they are missing, record `frontmatter_invalid` (info).

Verified: a U+200B placed inside `MEMORY.md` defeats today's only rule. Step 5 closes that gap, and the attempt itself becomes a finding.

---

## 9. Static stage — Semgrep (`static/semgrep.py`)

### 9.1 Resolving the binary

1. `static.semgrep_path` from config, if it is set.
2. `Path(sys.executable).parent / "semgrep"` (`semgrep.exe` on Windows). `pipx` and `uv tool` install the package's dependencies into their own environment and don't put a dependency's console script on PATH, so this lookup comes first.
3. `shutil.which("semgrep")`.

If none of these finds it → `semgrep_unavailable` (error). The message tells the user to reinstall skill-warden.

### 9.2 Invocation

```text
semgrep scan --json --metrics=off --disable-version-check --scan-unknown-extensions
             --timeout 20 --config <bundled rules dir> [--config <extra>...]
             <every normalized text file, listed explicitly> <liveness target>
```

- The working directory is the normalized temp directory.
- The subprocess environment is minimal (PATH, HOME, LANG). It never includes the user's API keys.
- The subprocess timeout is `static.timeout_seconds` (default 60).
- **Never pass a directory as a target.** Verified: with a directory target, a `.semgrepignore` shipped inside the skill silently drops `SKILL.md` from the scan. Explicit file targets are scanned even when they're listed in that file.

### 9.3 Result handling

| Observation | Finding |
| --- | --- |
| Binary not found | `semgrep_unavailable` (error) |
| Subprocess exceeds the timeout | `semgrep_timeout` (error) |
| Exit code is not 0 | `semgrep_failed` (error), with the exit code in the detail. Verified: a rule parse error exits 2 and a missing config exits 7, both with `results: []` |
| stdout isn't JSON, or has no `results` list | `semgrep_failed` (error) |
| An `errors[]` entry has `level: "error"` | `semgrep_error` (error). `warn` entries become `info` |
| A requested target is missing from `paths.scanned` | `target_not_scanned` (error). This generalizes today's `skill_md_skipped` |
| The liveness canary hit is missing | `semgrep_liveness_failed` (error) |
| Each entry in `results` | One finding, with severity mapped as below, and `line` from `start.line` |
| None of the above, and no results | `semgrep.ok` (info) |

Severity map, unchanged: `ERROR`, `CRITICAL` and `HIGH` map to `high`. `WARNING` and `MEDIUM` map to `medium`. `LOW` maps to `low` and `INFO` to `info`. Anything else maps to `error`.

**Liveness canary.** Each scan adds one synthetic target, `.warden-liveness-<nonce>.txt`, that holds a random token. A bundled INFO rule, `warden-liveness`, matches it. The stage requires exactly that one hit and then removes it from the findings. This catches a Semgrep run that loaded no rules, skipped targets without saying so, or returned an empty result by mistake. It is the static stage's counterpart to the reader's prompt canary.

### 9.4 Rules

- The bundled rules are package data in `skill_warden/rules/`. The SHA-256 of that directory is recorded in every report.
- Users can add extras with `--rules DIR` or `static.extra_configs`. Local paths are recommended.
- Registry IDs such as `p/ai-best-practices` are accepted, but they fetch over the network, the liveness check doesn't cover them, and their license should be checked before anyone vendors them.
- `.semgrep.yml`, `.semgrepignore` and `.gitignore` files from the skill are scanned as text and never obeyed.

The MVP rule set is listed below. Every rule needs inert fixtures that use `example.invalid`, `EXAMPLE_TOKEN` and `FAKE-CANARY`. Describe detections in docs by category, not as recipes.

| Category | Severity | Signal (described, not reproduced) |
| --- | --- | --- |
| Memory or config persistence instruction | high | An instruction to write or append to `MEMORY.md`, `CLAUDE.md` or agent memory (today's rule, fixed) |
| Agent permission or hook tampering | high | Permission-bypass settings or flags; adding hooks to agent settings files |
| Credential store access | medium; high when near an outbound transfer | Cloud and CLI credential files, private SSH keys, `.env`, `.netrc`, agent config keys |
| Download-and-execute | high | Remote content piped into an interpreter |
| Decode-and-execute | high | A decoded blob handed to a shell or `eval` |
| Outbound transfer of local data | high | File contents or environment values posted to a URL |
| Persistence outside the skill | high | Shell rc files, crontab, git hooks, other skills' directories |
| Hidden instructions | high | Markup comments that contain override phrasing aimed at the AI |
| Safety-claim language | medium | "Security audited", "verified safe", "do not scan" |
| Liveness canary | info (filtered out) | The synthetic token |

Fix the existing rule when it moves. In `rules/memory.yaml`, the `>-` folded scalar joins the two regex lines with a space, so the pattern only matches when a space comes right before `MEMORY.md`. Verified: `append the note to ./MEMORY.md` is missed. Write each regex as a single-line quoted scalar.

After the generic set, add language-aware rules for `scripts/*.py` and `scripts/*.sh` using Semgrep's `python` and `bash` languages. That is the strongest reason to keep Semgrep.

---

## 10. Reader stage — provider-agnostic LLM (`llm/`)

### 10.1 When it runs

The reader is off unless config has an `[llm]` table or the user passes `--llm PROVIDER:MODEL`. `--no-llm` always turns it off. When it is on and fails, the scan is BLOCK: a review that was requested and didn't happen is not a pass.

### 10.2 Containment

1. **The system prompt is fixed.** Untrusted bytes appear only in the user message, between per-call random boundary markers (`<<SKILL-6f2c…>>` … `<</SKILL-6f2c…>>`). Each file has a `=== FILE: relpath ===` header.
2. **The model never gets tools.** Adapters never send `tools` or `tool_choice`.
3. **The output contract** is `{"flags": [...], "evidence": [...]}` and nothing else.
   - The allowed flags are the four high ones (`indirect_injection`, `credential_exfil`, `memory_persistence`, `shell_callback`) and the two medium ones (`false_safety_claim`, `obfuscation`).
   - There is no verdict field, so an injected "output ALLOW" has nowhere to land.
4. **A random canary** sits in the system prompt. If it appears anywhere in the response, the result is `reader_canary_echoed`.
5. **The response is data.** It goes through `json.loads` and is never executed, never rendered as markup, and never fed into another prompt.
6. **One call per skill.**

Requirements for the system prompt template:

- Say that the content between the boundary markers is untrusted data written by a third party, and that instructions inside it are things to report, not obey.
- Define each flag:

  | Flag | Definition |
  | --- | --- |
  | `indirect_injection` | Text that tries to change the agent's goals or instructions |
  | `credential_exfil` | Reading secrets, then sending, printing or storing them |
  | `memory_persistence` | Writing to agent memory, config or hooks so instructions outlive the skill |
  | `shell_callback` | Remote connections for command execution or data transfer beyond the stated purpose |
  | `false_safety_claim` | Claims of being audited or safe, or requests not to review |
  | `obfuscation` | Encoded or disguised content whose purpose is hidden |

- Ask for 0–10 short evidence quotes.
- Restate the exact JSON shape.
- End with the canary line.

### 10.3 Input

- Only normalized text files (§8, step 5) are sent: `SKILL.md` first, then other Markdown, then `scripts/`, then everything else.
- Each binary file appears as a single line with its name only.
- If the payload is over `llm.max_input_chars` (default 60,000), the result is `reader_input_too_large` (error). The text is never truncated silently: text the model didn't read is text nobody reviewed.

### 10.4 Parsing the output

1. Strip surrounding whitespace.
2. If the whole text is wrapped in exactly one Markdown code fence (` ``` ` or ` ```json `), unwrap it. Small local models do this even in JSON mode, and without this step every Ollama user would get BLOCK.
3. Run `json.loads`. The result must be an object with exactly the keys `flags` and `evidence`. Both must be lists of strings, and every flag must come from the allowed set.
4. Anything else is `reader_invalid`. Don't use heuristics such as "find the first `{`".

A valid response with no flags → `reader.ok` (info). With flags → one finding per flag; the excerpt is the redacted evidence, joined and capped. This is the existing `findings._reader_rows` behavior.

### 10.5 Failure taxonomy

All of these are BLOCK. Each has its own reason so that a configuration mistake never looks like a malicious skill.

| `rule_id` | Causes | What the user does |
| --- | --- | --- |
| `reader_unavailable` | Connection refused, DNS failure, timeout, 401 or 403, 404 for the model, 429 or 5xx or overloaded after retries, the API-key variable unset, the `[anthropic]` extra missing, a 400 from parameters the model rejects | Fix the config, start the local server, or pass `--no-llm` |
| `reader_invalid` | Not JSON, wrong shape, unknown flag, truncated output (`finish_reason: "length"` or `stop_reason: "max_tokens"`) | Raise `max_output_tokens`, or pick a model that follows JSON instructions |
| `reader_canary_echoed` | The system canary appears in the response | Treat the skill as hostile: it tried to extract or steer the reader |
| `reader_refused` | A provider safety refusal: OpenAI `message.refusal`, or Anthropic `stop_reason: "refusal"` | Review the skill by hand. A refusal triggered by a skill's text is suspicious in itself |
| `reader_input_too_large` | The payload is over the cap | Raise the cap if the skill is legitimate |

One non-error reader finding is related: `reader_primary_refused` (medium). It means the configured model refused, but a provider fallback model answered (§10.8). The verdict is at least ASK, so a fallback can't turn a refusal into ALLOW.

Retry transient errors only: connection errors, 408, 409, 429 and 5xx. Retry at most twice and honor `Retry-After`. Never retry invalid output.

Hosted models whose safety systems decline to analyze attack text surface as `reader_refused`. That is the defender's guardrail asymmetry. A local open-weight model avoids it, usually at some cost in judgment.

### 10.6 Adapter interface

```python
@dataclass(frozen=True)
class ReaderRequest:
    system: str
    user: str
    schema: dict              # the JSON schema of the output contract
    max_output_tokens: int

class ReaderClient(Protocol):
    label: str                # e.g. "ollama:qwen2.5:7b", printed in coverage
    def complete(self, request: ReaderRequest) -> str: ...
    # Returns the raw response text, or raises ReaderError(kind, detail)
    # with kind in {"unavailable", "invalid", "refused"}.
```

`llm/reader.py` owns everything provider-independent:

- building the prompt, boundaries, canary and payload;
- calling `client.complete()`;
- parsing (§10.4);
- mapping results and errors to findings (§10.5).

Adapters only move bytes and classify transport and provider errors. They never see flag logic. Tests inject fakes at the `ReaderClient` seam.

Output schema, used where the provider can enforce it and always re-validated locally:

```json
{
  "type": "object",
  "properties": {
    "flags": {"type": "array", "items": {"type": "string", "enum": [
      "indirect_injection", "credential_exfil", "memory_persistence",
      "shell_callback", "false_safety_claim", "obfuscation"]}},
    "evidence": {"type": "array", "items": {"type": "string"}}
  },
  "required": ["flags", "evidence"],
  "additionalProperties": false
}
```

### 10.7 OpenAI-compatible adapter (`llm/openai_compat.py`, httpx)

This one adapter covers OpenAI, OpenRouter, Groq, Gemini's OpenAI-compatible endpoint, Ollama, LM Studio, vLLM and the llama.cpp server.

- **Request:** `POST {base_url}/chat/completions`. Send `Authorization: Bearer <key>` only when a key is configured. Local servers usually need none, and Ollama ignores it.
- **Body:**
  - `model`;
  - `messages`: a system message and a user message;
  - the token limit, under the configured name: `max_completion_tokens` for OpenAI, `max_tokens` for most others;
  - `response_format`, according to `json_mode`;
  - `temperature`, only if it is set in config.
- **Never send `tools` or `tool_choice`.** Ollama documents `tool_choice` as unsupported and documents `max_tokens` but not `max_completion_tokens`. Today's reader sends `tool_choice: "none"`, `max_completion_tokens` and `temperature: 0`, which is why it isn't portable.
- **`json_mode`:** `json_schema` sends `{"type": "json_schema", "json_schema": {"name": "skill_warden_reader", "schema": <§10.6 schema>, "strict": true}}`. The `name` field is required by OpenAI-style APIs; without it the first live call fails with a 400. `json_object` asks for JSON mode. `none` relies on the prompt alone; the parser is still strict.
- **Response:** read `choices[0].message.content`. `finish_reason == "length"` means truncated. A non-null `message.refusal` means refused.

**Presets** are conveniences; the user can override every field. `model` is always required and has no default, because a stale default model name turns into a 404 and then a BLOCK.

| provider | base_url | api_key_env | token_param | json_mode |
| --- | --- | --- | --- | --- |
| `openai` | `https://api.openai.com/v1` | `OPENAI_API_KEY` | `max_completion_tokens` | `json_schema` |
| `ollama` | `http://localhost:11434/v1` | none | `max_tokens` | `json_object` |
| `openai-compatible` | required | optional | `max_tokens` | `json_object` |

Examples of `openai-compatible` endpoints, which must be checked with `doctor --llm` before anyone relies on them:

- LM Studio: `http://localhost:1234/v1`
- OpenRouter: `https://openrouter.ai/api/v1`
- Groq: `https://api.groq.com/openai/v1`
- Gemini: `https://generativelanguage.googleapis.com/v1beta/openai`
- vLLM and llama.cpp: their `/v1`

Only the Ollama row was checked against its documentation for this document.

### 10.8 Anthropic adapter (`llm/anthropic.py`, official SDK, extra `skill-warden[anthropic]`)

Claude is called through Anthropic's official Python SDK, not through an OpenAI-compatible shim, following Anthropic's guidance. The SDK is an optional extra so that the core install stays small.

- **Call:**

  ```python
  client.messages.create(
      model=model,
      max_tokens=max_output_tokens,
      system=SYSTEM,
      messages=[{"role": "user", "content": USER}],
      output_config={"format": {"type": "json_schema", "schema": READER_SCHEMA}},
  )
  ```

  With `output_config.format`, the first text block is valid JSON for the schema. The strict local parser still runs.
- **Don't send `temperature`.** Current Claude models return a 400 for sampling parameters.
- **Don't send `thinking`.** Opus 5.5 always thinks and returns a 400 for `{"type": "disabled"}`. Determinism comes from the schema and the validator, not from temperature.
- **Don't set `max_tokens` too low.** Thinking counts against it. The adapter default is 4096. `stop_reason == "max_tokens"` → `reader_invalid`.
- **Refusals.** `stop_reason == "refusal"` on the final response → `reader_refused`, with `stop_details.category` recorded in the detail. That final refusal means every model in the fallback chain declined.
- **Refusal fallbacks.** Anthropic recommends opting into server-side refusal fallbacks for Opus 5.5, Sonnet 5.5 and Fable 5.1 on the Claude API.
  - The shape is `fallbacks: "default"` with beta `server-side-fallback-2026-07-01`. That is a beta call: `client.beta.messages.create(..., betas=["server-side-fallback-2026-07-01"], fallbacks="default")`, not `client.messages.create`.
  - Make it `llm.refusal_fallback`, on by default for those models. Haiku 5.5 rejects `fallbacks`.
- **A fallback must not erase the refusal signal.** §10.5 treats a refusal as suspicious. If fallbacks are on and a fallback model answered, the reader must still add `reader_primary_refused` (medium), so the verdict is at least ASK even when the fallback model returns no flags.
  - Detect a fallback from a `fallback` content block, or from a `usage.iterations` entry of type `fallback_message`.
  - Record the model that answered (`response.model`) in history as `reader_answered_by`.
  - Because `fallback` blocks can appear in `content`, read the first block whose `type == "text"`, never `content[0]`.
- **Effort.** `llm.effort` is optional and maps to `output_config.effort` (`low` … `max`). When unset, the model's default applies, which is `medium` on Opus 5.5.
- **Errors.** The SDK raises typed exceptions and already retries 408, 409, 429 and 5xx, twice by default.
  - Authentication, permission, not-found, rate-limit, server, connection and timeout errors → `reader_unavailable`.
  - `BadRequestError` → `reader_unavailable`, with the API message attached, because a 400 here is a configuration problem.
- **Key.** Pass the key explicitly: `api_key=os.environ[api_key_env]`. That way the variable the user configured wins over the SDK's own credential lookup.
- **httpx2.** `anthropic` 1.x is built on `httpx2`, not `httpx`, so never pass core `httpx` objects into it. Pin the SDK's current major version when implementing; check PyPI.
- **Model.** The model is the user's choice. The examples in this repository use `claude-opus-5-5`.
- **Out of scope for the MVP:** Claude on Bedrock, Vertex and Foundry. Those need the SDK's platform clients (§19).

### 10.9 Keys and privacy

- Keys are read at call time from the environment variable named in config (`api_key_env`).
  - `init` never asks for a key.
  - Config files never contain one.
  - Reports and history never include one.
  - Semgrep and the jail never receive the process environment.
- With a hosted provider, the skill's text leaves the machine. With Ollama, LM Studio or vLLM on localhost, it does not. `doctor` and the coverage line say which case applies.
- The reader receives only the skill's own text. It never sees honeytoken values, detonation logs, or anything from the user's environment.

---

## 11. Detonation stage (opt-in, `detonate/`)

### 11.1 Scope

The jail runs the skill in four phases, each under `strace` as uid 10001 in a hardened container (R22, R23):

1. `install`: declared install steps and setup blocks;
2. `scripts`: every shell, Python and Node script under `scripts/`, run with no arguments, with `--help`, and with each example from `SKILL.md`;
3. `skill_md`: the remaining `bash` and `sh` blocks;
4. `agent`: a victim agent loads `SKILL.md` and acts on it through tool calls executed inside the jail. The model must be a local, loopback endpoint, because tool output carries canary values.

The container's home holds a lived-in set of per-run, format-valid honeytokens (§11.7), and its only network neighbor is a sink that answers everything (§11.4). Each skill runs under four profiles (`laptop`, `ci`, `+30d`, `+365d`). A profile whose sensitive behavior differs from `laptop`'s is itself a finding.

Coverage is checked, not assumed. A planned phase or script that left no `execve`, or an agent phase with no model turn, gives `coverage_incomplete` (error), which is BLOCK `tool_error`. So `--detonate` without a local agent model is BLOCK.

Detonation catches payloads that act. The reader covers payloads that only give instructions. Attacks that live only in the wording of `SKILL.md` are the reader's job.

The refactor guide's R15–R25 build this. They adapt `docs/build-guide.md` Steps 19–26.

### 11.2 Requirements

- A Docker Engine the CLI can reach, running Linux containers.
- Support for `--internal` networks with `com.docker.network.bridge.gateway_mode_ipv4=isolated`. Docker's docs say that `isolated` requires `--internal` and assigns no address to the bridge. They don't say which engine version introduced it.

So `doctor --docker` creates and removes a throwaway network to probe for support, rather than comparing version numbers. The hackathon tests ran with this setting on Docker Desktop 28.5.1 (macOS).

### 11.3 Images

- The build contexts ship as package data (`skill_warden/docker/jail`, `skill_warden/docker/sink`) and are opened with `importlib.resources.as_file`.
- Tags are content-addressed: `skill-warden-jail:<first 12 hex of the context's sha256>`.
- An image is built only when `docker image inspect` doesn't find it. `doctor --docker` pre-builds both.
- The first build needs network access to pull `alpine` and its `apk` packages. Pin the base images by digest.

Today both images are rebuilt on every detonation, and their contexts are found via `parents[2]`, which breaks once the package is installed from a wheel.

### 11.4 Per-run resources

| Resource | Name | Configuration |
| --- | --- | --- |
| Network | `sw-<run8>` | `--internal`, `--ipv6=false`, `gateway_mode_ipv4=isolated`, subnet chosen by Docker IPAM |
| Sink | `sw-sink-<run8>` | dnsmasq answers every name with the sink's own address, never NXDOMAIN. An HTTP catch-all on :80 logs the request line and body. TLS on :443 and through `CONNECT` uses a per-run CA whose key never leaves the sink, and the SNI is logged before the handshake finishes. Every other TCP port is redirected to one logging listener. The sink alone gets `NET_ADMIN` for that redirect. Fetched script paths get an inert body that only touches a per-run marker (`remote_exec`). The entrypoint finds its own IP at startup instead of being given a fixed `SINK_IP` |
| Jail | `sw-jail-<run8>` | Flags from §11.5, plus `--dns <sink ip>`, `HTTP_PROXY`/`HTTPS_PROXY=http://<sink ip>:80`, the CA bundle variables pointing at the run's CA certificate, and the honeytoken env baits |

Lifecycle:

- Every resource carries the labels `skill-warden.run=<run_id>` and `skill-warden.created=<unix time>`.
- Teardown runs in `finally` and removes only this run's resources.
- On startup, the CLI removes labeled resources older than one hour, which are leftovers from crashed runs.
- Logs are read from this run's sink object, never from a module-level cache.

Today's fixed `jailnet`, `skill-warden-sink` and `172.30.15.0/24` collide with VPN routes and with a second concurrent run. Today's `_cleanup_labeled()` also deletes any other run's sink.

### 11.5 Jail hardening (kept)

- **Capabilities:** `--cap-drop=ALL`, plus `SETUID` and `SETGID` so the entrypoint can drop to uid 10001. `--security-opt no-new-privileges`.
- **Filesystem:** `--read-only`. tmpfs mounts for `/tmp` and `/home/agent` (64m, nosuid, nodev).
- **Limits:** `--pids-limit 128`. `--memory 256m`, with `--memory-swap` set to the same value.
- **Isolation:**
  - no bind mounts, no `docker.sock`;
  - no host environment (only explicit `-e`);
  - the runner interface takes no `env` parameter.
- **Inputs:** The skill and the home directory are streamed in with tar. `pack_skill` refuses any symlink that escapes the skill.
- **Scratch:** Each run builds the honeytoken home in a fresh `TemporaryDirectory`. Today it reuses `scratch/home` and cleans it with a fragile loop.
- **Phase timeout:** 60 s. When it fires, the result is a `delay` finding and a `docker kill`.
- **Runtime:** `runsc` (gVisor) when `docker info` lists it. Otherwise runc, which must be at or above 1.2.8 on 1.2.x or 1.3.3 on 1.3.x (the November 2025 escape fixes).
- **Isolation check, fail closed (R18):** before any skill bytes enter the jail, Warden checks three things. It checks the host runtime version. It checks the container's `docker inspect` (not privileged, no host namespaces, only the plan's tmpfs mounts, no `docker.sock`, this run's network). And it runs an in-jail probe as uid 10001 that checks for zero capabilities, `NoNewPrivs`, seccomp mode 2, a read-only root, a non-root uid and no direct route out. Any failure → `isolation_failed` (error) → BLOCK `tool_error`, with no skill bytes streamed. Raw inspect output never reaches a finding, because its environment holds bait values.
- **Written files:** `docker diff` doesn't see tmpfs writes, so after each phase the jail lists the files under `/home/agent` and `/tmp` that are newer by mtime or ctime than a per-run start marker. They are tarred out (4 MB cap), and the host reads them in memory only.

### 11.6 Observation → findings (kept)

| Event | Finding |
| --- | --- |
| A honeytoken file opened | `canary` / `honeytoken` / critical, excerpt `[canary tripped]` |
| Any canary registry value (plants, env baits, nonce) found in egress (DNS, HTTP, TLS, TCP logs), execve argv, or written-file contents. The search covers raw, base64 at every alignment, hex, URL, JSON, base32 and gzip forms, and DNS labels with the dots removed | `canary` / `canary_egress` \| `canary_argv` \| `canary_file` / critical |
| A fetched inert payload's marker appears, or a file written during the run is executed | `jail` / `remote_exec` / high |
| A Host, SNI or DNS name on `rules/exfil_hosts.txt` | `jail` / `exfil_channel` / high |
| An install-phase index request for an undeclared package | `jail` / `undeclared_fetch` / high |
| The sensitive rule set differs between profiles | `jail` / `profile_divergence` / high |
| Weaker environment reads (`mountinfo`, DMI, `cpuinfo`) | `jail` / `env_probe` / medium |
| `connect` to anything other than the sink | `jail` / `egress` / high |
| A read of `/.dockerenv`, `/proc/1/cgroup` or `TracerPid` | `jail` / `sandbox_probe` / high |
| A write to a shell rc file, `.git/hooks`, cron, user services or autostart, `authorized_keys`, Python startup hooks, package-manager config, agent instruction files or MCP configs, or another skill's directory | `jail` / `persistence` / high |
| A sleep longer than 30 s, or the phase timeout | `jail` / `delay` / high |
| strace dies, or something reads `TracerPid` | `jail` / `observer_attack` / high |
| A completed run with no `jail` findings | `jail` / `jail.ok` / info |
| Docker missing or unreachable; isolated mode unsupported | `jail` / `detonation_unavailable` / error |
| An isolation check fails | `jail` / `isolation_failed` / error |
| A planned phase or script didn't run, or the agent phase had no model turn | `jail` / `coverage_incomplete` / error |
| An image build, network, container or stream step fails | `jail` / `detonation_failed` / error |

### 11.7 Honeytokens (kept)

Each run gets a fresh nonce and a fresh, lived-in home (R19):

- format-valid credentials, generated per run, at the paths real tools read: cloud, SSH, git forge, package registries, container and cluster config, agent config, a project `.env`, a wallet and a browser credential store;
- the original nonce-bearing plants and the `MEMORY.md` breadcrumb, kept at their paths;
- env bait variables with generated values;
- wear and tear, with spread-out mtimes, because an empty home is a sandbox tell.

A format-valid value can't contain the nonce, so a per-run canary registry holds every plant value, every bait value and the nonce. Detection searches for all of them. All of them go on the run's redaction list, and history and rendering refuse any of them in any encoding `canary.find` knows. A canary touch is BLOCK whatever the skill claims to be for.

---

## 12. Policy (`policy.py`)

`decide(outcome: RunOutcome) -> Verdict`. It is pure: no I/O, no clock, no model. The first matching row wins.

| # | Condition | Decision | reason |
| --- | --- | --- | --- |
| 1 | `status == "timeout"` | BLOCK | `timeout` |
| 2 | `status != "completed"` | BLOCK | `not_finished` |
| 3 | No findings at all | BLOCK | `no_findings` |
| 4 | Any finding with `source == canary` | BLOCK | `canary` |
| 5 | Any finding with `source == reader` and severity `error` | BLOCK | `reader_error` |
| 6 | Any other finding with severity `error` | BLOCK | `tool_error` |
| 7 | Any finding with severity `high` or `critical` | BLOCK | `high_finding` |
| 8 | `static` was requested and there is no non-error `semgrep` finding | BLOCK | `semgrep_missing` |
| 9 | `reader` was requested and there is no non-error `reader` finding | BLOCK | `reader_missing` |
| 10 | `detonation` was requested and there is no non-error `jail` finding | BLOCK | `detonation_missing` |
| 11 | Any finding with severity `medium` | ASK | `medium_only` |
| 12 | Otherwise | ALLOW | `clean` |

`Verdict.detail` is the `rule_id` of the first finding that satisfied the deciding row, so the user can see what to fix (for example `tool_error` / `semgrep_failed`). For rows 1–3 and 8–10, which no single finding decides, `detail` is empty. The sentinels `semgrep.ok`, `reader.ok` and `jail.ok` are emitted only when a stage completed with nothing else to report, which matches today's `semgrep.ok` behavior. Rows 8–10 catch a stage that returned without doing anything.

Porting the 19 ClickHouse cases from `tests/test_verdict_sql.py`:

| Old case | v2 equivalent | Expected |
| --- | --- | --- |
| `missing_run`, `young_running`, `finished_at_null` | `status="error"` (the pipeline always has an outcome) | BLOCK `not_finished` |
| `duplicate_run`, `stalled_running` | ClickHouse artifacts: drop them. A stalled run is now `status="timeout"` | BLOCK `timeout` |
| `timeout` | `status="timeout"` | BLOCK `timeout` |
| `no_findings` | completed, no findings | BLOCK `no_findings` |
| `canary` | canary critical | BLOCK `canary` |
| `reader_error` | reader error + `semgrep.ok` | BLOCK `reader_error` |
| `policy_error`, `semgrep_error` | intake or semgrep error | BLOCK `tool_error` |
| `jail_high`, `high`, `critical`, `high_plus_medium` | as before | BLOCK `high_finding` |
| `reader_medium` | reader medium, no semgrep row, static requested | BLOCK `semgrep_missing` |
| `semgrep_medium` | semgrep medium | ASK `medium_only` |
| `clean_info`, `low_only` | `semgrep.ok`, or semgrep low | ALLOW `clean` |

New cases:

| Case | Expected |
| --- | --- |
| reader requested, no reader rows | BLOCK `reader_missing` |
| detonation requested, no jail rows | BLOCK `detonation_missing` |
| static only, `semgrep.ok` | ALLOW `clean` (shown as "static only") |
| `reader_refused` | BLOCK `reader_error` |
| `reader_primary_refused` (fallback answered, no flags) + `semgrep.ok` | ASK `medium_only` |
| intake `symlink` | BLOCK `tool_error` |
| `obfuscation.unicode` + `semgrep.ok` | ASK `medium_only` |
| `jail` / `isolation_failed` (error) + `semgrep.ok` | BLOCK `tool_error`, detail `isolation_failed` |
| `jail` / `coverage_incomplete` (error) + other `jail` findings | BLOCK `tool_error`, detail `coverage_incomplete` |
| `jail` / `env_probe` (medium) + `semgrep.ok`, nothing stronger | ASK `medium_only` |

Properties to test:

- The same input always gives the same output.
- Once a canary, error, high or critical finding is present, adding any further finding never changes the decision. This is what makes the short-circuit in §7.2 safe.

---

## 13. History (`history.py`)

- Uses stdlib `sqlite3`. The file is `<data dir>/history.sqlite3` (§14.3). `--no-history` turns it off.
- The DDL is package data, `schema/history.sql`:

```sql
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, skill_path TEXT NOT NULL, skill_name TEXT NOT NULL,
  content_sha256 TEXT, started_at TEXT NOT NULL, finished_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('completed','timeout','error')),
  stages TEXT NOT NULL,            -- JSON list of requested stages
  coverage TEXT NOT NULL,          -- JSON {stage: status}
  tool_version TEXT NOT NULL, semgrep_version TEXT, rules_sha256 TEXT,
  reader_label TEXT,               -- provider:model as configured
  reader_answered_by TEXT          -- model that actually answered (differs after a fallback)
);
CREATE TABLE IF NOT EXISTS findings (
  run_id TEXT NOT NULL REFERENCES runs(run_id), source TEXT NOT NULL, rule_id TEXT NOT NULL,
  severity TEXT NOT NULL CHECK (severity IN ('info','low','medium','high','critical','error')),
  file TEXT NOT NULL, line INTEGER, excerpt TEXT NOT NULL, evidence_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS verdicts (
  run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
  decision TEXT NOT NULL CHECK (decision IN ('BLOCK','ASK','ALLOW')),
  reason TEXT NOT NULL, detail TEXT NOT NULL,
  payload_hash TEXT NOT NULL, prev_hash TEXT NOT NULL, decided_at TEXT NOT NULL
);
```

**Writes.**

- Each run is written in one transaction, opened with `BEGIN IMMEDIATE` so that two CLIs running at once can't fork the chain.
- `payload_hash` is the SHA-256 of the canonical JSON (sorted keys, compact separators) of `{run_id, content_sha256, decision, reason, detail, findings_digest, tool_version, rules_sha256, decided_at, prev_hash}`.
- `prev_hash` is the previous verdict's `payload_hash`, or `""` for the first one.
- `findings_digest` is the SHA-256 over the sorted `(source, rule_id, severity, file, line, evidence_hash)` tuples.
- `history --verify` recomputes the chain.
- The writer refuses any excerpt that contains a run secret. The whole transaction rolls back.

**What it claims:** edits made without recomputing the chain are detected. It does not stop someone with write access from rewriting the whole chain; signing is on the roadmap.

**Write failures:** a failed history write prints a warning. It changes neither the verdict nor the exit code.

---

## 14. Configuration (`config.py`, `paths.py`)

### 14.1 Sources and precedence

The order is: CLI flags, then environment variables (`SKILL_WARDEN_*`), then `--config FILE` or the user config file, then built-in defaults.

No project-level config file is ever read implicitly. A cloned repository must not be able to configure the scanner that is about to judge its skills (principle 6).

Config is parsed with `tomllib` (stdlib) and validated strictly: an unknown key or a wrong type is exit 2, and the message names the key path.

### 14.2 Example

```toml
# ~/.config/skill-warden/config.toml
[scan]
timeout_seconds = 300
short_circuit = true
history = true

[intake]
max_files = 500
max_total_bytes = 5_242_880
max_file_bytes = 1_048_576

[static]
extra_configs = []            # local rule paths; registry ids need network
timeout_seconds = 60

[llm]                         # delete this table to keep the reader off
provider = "ollama"           # openai | anthropic | ollama | openai-compatible
model = "qwen2.5:7b"          # always explicit
# base_url = "http://localhost:11434/v1"
# api_key_env = "OPENAI_API_KEY"     # the NAME of the variable, never the key
# json_mode = "json_object"          # json_schema | json_object | none
# token_param = "max_tokens"         # or max_completion_tokens
max_output_tokens = 1024
max_input_chars = 60000
timeout_seconds = 120
# temperature = 0                    # only for providers that accept it
# effort = "low"                     # anthropic only
# refusal_fallback = true            # anthropic only

[detonation]
phase_timeout_seconds = 60
memory = "256m"
pids_limit = 128

[discovery]
roots = ["~/.claude/skills", ".claude/skills"]
```

### 14.3 Paths

| | Order of lookup |
| --- | --- |
| Config | `$SKILL_WARDEN_CONFIG`, then `$XDG_CONFIG_HOME/skill-warden/config.toml`, then `~/.config/skill-warden/config.toml` (macOS and Linux) or `%APPDATA%\skill-warden\config.toml` (Windows) |
| Data | `$SKILL_WARDEN_HOME`, then `$XDG_DATA_HOME/skill-warden`, then `~/.local/share/skill-warden` or `%LOCALAPPDATA%\skill-warden` |

This avoids a `platformdirs` dependency.

---

## 15. Packaging and distribution

**Layout.**

- The code lives in `src/skill_warden/`.
- Package data:
  - `rules/*.yaml`, including `warden-liveness`;
  - `docker/jail/*` and `docker/sink/*`;
  - `schema/history.sql`;
  - `selftest/clean/` and `selftest/memory/`, two tiny inert skills used by `doctor`.

**`pyproject.toml`.**

- Build backend `hatchling`.
- `requires-python = ">=3.11"`, for `tomllib` and `StrEnum`.
- Dependencies: `httpx`, and `semgrep>=1.180,<2` (the tested version is the lower bound).
- Extra: `anthropic = ["anthropic"]`, pinned to the current major when implemented.
- Script: `skill-warden = "skill_warden.cli:main"`.

**Resources.** Everything is loaded via `importlib.resources.files("skill_warden")`. Nothing walks `parents[2]` or looks in the working directory, as `verdict.load_sql`, `jail` and `sink` do today.

**Install.**

- Recommended: `pipx install skill-warden` or `uv tool install skill-warden`.
- `pip install skill-warden` inside a venv also works.
- Claude users install `'skill-warden[anthropic]'`.

**Platforms.** macOS and Linux are the targets. Semgrep announced native Windows support in its November 2025 release, so the static and reader stages should work on Windows. Detonation there needs Docker Desktop with Linux containers. Call Windows untested until CI covers it.

**Release check.** This is the real acceptance test:

1. Build the wheel.
2. Install it into a fresh venv.
3. `cd` to a directory outside the repository.
4. Run `skill-warden doctor` and `skill-warden scan` on the packaged self-test skills.

A suite that passes from the repository root doesn't prove the package works once installed.

Check that the name `skill-warden` is free on PyPI before publishing.

---

## 16. Testing strategy

### 16.1 Layers

| Layer | Marker | Needs | Runs by default |
| --- | --- | --- | --- |
| Unit | none | Python | yes |
| Semgrep-backed | none | `semgrep` (a dependency) | yes |
| Docker | `docker` | a running Docker engine | no (`pytest -m docker`) |
| Live LLM | `live_llm` | provider environment variables | no |
| Packaging | `packaging` | `build` and a temporary venv | no (CI) |

Set `addopts = "-m 'not docker and not live_llm and not packaging'"`. A contributor without Docker then gets a green suite, and CI runs the Docker job on Linux. The hackathon rule "a skipped test fails the step" fit an agent-driven build guide; explicit markers replace it here.

### 16.2 Required test groups

- **Policy:** the table in §12, including the ported cases and the monotonicity property.
- **Fail-closed regressions:** one test per defect in §17.1.
- **Reader contract:**
  - `httpx.MockTransport` for the OpenAI-compatible adapter, and a fake injected at the `ReaderClient` seam for Anthropic;
  - each kind of error;
  - fence unwrapping, canary echo, truncation and refusal;
  - checks that `tools`, `tool_choice` and `temperature` are absent from request bodies.
- **Detection golden table:** fixture → expected decision, reason and rule IDs, run static-only and with a scripted reader. The expected rows are in `docs/v2/refactor-guide.md` (R26). Detonation has its own labeled matrix, `fixtures/eval/manifest.json` (R25).
- **CLI:**
  - exit codes;
  - a snapshot of the JSON envelope;
  - the worst verdict across several paths;
  - coverage labels;
  - one skill's internal error not aborting the others.
- **Packaging smoke test** (§15).
- **Docker:**
  - `steal-key` → BLOCK;
  - `clean-date` → ALLOW;
  - the nonce never appears in history excerpts;
  - no labeled resources remain after a run;
  - two concurrent runs don't interfere;
  - the isolation check passes on a supported runtime, and a failed check streams no skill bytes;
  - the eval matrix: every malicious fixture is BLOCK, and benign look-alikes match their expected decision. Precision, recall, F1, MCC, the ASK rate and the `tool_error` rate are reported per behavior and per evasion class;
  - a leak test over every persisted artifact, a mutation test that disables redaction and must make it fail, and a seeded property test over every channel and encoding.

---

## 17. Failure modes and mitigations

### 17.1 Defects in today's code that the refactor must fix

| # | Defect | Effect today | Fix |
| --- | --- | --- | --- |
| 1 | `findings._semgrep_rows` emits `semgrep.ok` whenever `results` is empty, ignoring the exit code and engine errors | A broken rule (exit 2) or a missing config (exit 7) → ALLOW. **Verified** | §9.3 |
| 2 | `semgrep.scan` raises when the binary is missing, on timeout, or when stdout is empty | A traceback instead of BLOCK | The stage returns a failed `StageResult` |
| 3 | Only `SKILL.md` is checked for being skipped | Any other file can go unscanned and still get `semgrep.ok` | `target_not_scanned` for every target, plus the liveness canary |
| 4 | No Unicode normalization | A zero-width character inside `MEMORY.md` defeats the rule. **Verified** | §8, step 5 |
| 5 | A folded-scalar regex in `rules/memory.yaml` | `./MEMORY.md` doesn't match. **Verified** | A single-line regex, plus a fixture |
| 6 | `_reader_body` reads every file as UTF-8 | A PNG in `assets/` crashes the scan | Text/binary classification (§8) |
| 7 | No cap on reader input | Unbounded API cost; provider 413 errors | `max_input_chars` → `reader_input_too_large` |
| 8 | `content_hash` raises on any symlink | A traceback instead of a verdict | Intake records a `symlink` finding |
| 9 | The reader sends `tool_choice`, `max_completion_tokens` and `temperature: 0` | Unsupported by Ollama; current Claude models reject `temperature` | A request shape per adapter (§10.7, §10.8) |
| 10 | Docker contexts and `verdict.sql` are found via `parents[2]` or the working directory | Breaks when installed from a wheel | `importlib.resources` |
| 11 | Fixed `jailnet`, subnet and sink name; `_cleanup_labeled` removes every labeled container | Collisions with VPN routes; concurrent runs kill each other | Per-run names and run-scoped cleanup |
| 12 | Images are rebuilt on every detonation | Slow, and needs network on every run | Content-addressed tags |
| 13 | Two pipelines: `jail.detonate` writes to the store without the reader; `Orchestrator._run_jail` has the reader but an injected runner | Behavior drifts between them | One pipeline (§7) |
| 14 | The runner interface receives the host environment minus a four-name denylist | Unused by `detonate()` today, but the interface invites a leak | No `env` parameter; the jail gets nothing from the host |
| 15 | `sink.http_log` falls back to a module-level `_cached_http_log` | A failed read returns the previous run's log, so the nonce search looks at the wrong data | Logs read from the run's sink object |
| 16 | `detonate()` reuses `scratch/home` and cleans it with a non-recursive loop | Nested leftovers break `rmdir`; plants could carry over between runs | A fresh `TemporaryDirectory` per run |

### 17.2 Operational failure modes

**Intake**

| Failure | Effect | Mitigation |
| --- | --- | --- |
| The skill vendors a huge tree (for example `node_modules`) | BLOCK `tool_error` (`too_large`) | The message names the cap. The user raises it knowingly |
| A text file that isn't UTF-8 | Warden can't read it | `undecodable_text` (medium) → at least ASK |
| The skill root is a symlink (a linked install) | None, on purpose | Resolved once and recorded as `info`. Symlinks inside the skill are errors |
| Two discovered roots point to the same skill | It is scanned twice | Dedupe by resolved path |

**Static**

| Failure | Effect | Mitigation |
| --- | --- | --- |
| A Semgrep upgrade changes its JSON | The parse could go quiet | The liveness canary and the scanned-target check fail closed. The version range is pinned |
| A registry config is requested while offline | `semgrep_failed` | BLOCK, with a clear message. Docs say registry packs need network |
| False positives on legitimate security-docs skills | ASK or BLOCK | The report names the exact rule and line. Content-pinned approvals are on the roadmap (§19) |
| The skill ships ignore files or a `.semgrep.yml` | None | Explicit targets, rules only from Warden, verified scan coverage |

**Reader**

| Failure | Effect | Mitigation |
| --- | --- | --- |
| The local server isn't running | BLOCK `reader_error` (`reader_unavailable`) | The message suggests `ollama serve` or `--no-llm`; `doctor --llm` |
| A small model answers in prose or with extra keys | `reader_invalid` | `json_mode` and fence unwrapping; recommend a model that follows JSON |
| A reasoning model uses up the token budget | `reader_invalid` (truncated) | Raise `max_output_tokens`. The Anthropic default is 4096 |
| A provider refuses to analyze attack text | `reader_refused` | Reported as such; manual review; a local model avoids it; Anthropic refusal fallbacks |
| Prompt injection makes the reader return no flags | A false negative from that stage only | No tools, strict schema, canary, and the reader can only add evidence. Static and detonation still run |
| Rate limits during a bulk `--installed` scan | Remaining skills get `reader_unavailable` | Sequential scanning, retries with `Retry-After`, `--no-llm` for bulk triage |
| Runaway cost | Spend | One call per skill, the input cap, short-circuit skips the call once BLOCK is certain, `doctor` announces paid calls |
| API key leakage | Credential exposure | Read from env at call time; never logged or stored; redaction list; not passed to subprocesses |

**Detonation**

| Failure | Effect | Mitigation |
| --- | --- | --- |
| Docker isn't running | BLOCK `tool_error` (`detonation_unavailable`) | The message says to start Docker or drop `--detonate` |
| The isolated gateway mode isn't supported | `detonation_unavailable` | Found by the `doctor --docker` probe |
| The first image build happens offline | `detonation_failed` | Run `doctor --docker` while online. Pin base digests |
| The skill detects the sandbox, or sleeps until the timeout | `sandbox_probe`, `env_probe`, `delay` or `profile_divergence` findings | Lived-in home, four profiles with libfaketime (best effort under musl). Still a partial gap |
| HTTPS exfiltration | Captured through the per-run CA | A pinned client that aborts still leaves its SNI. Traffic to a hard-coded IP has no route and is an `egress` finding |
| A container escape | Lands in the Docker Desktop VM (macOS, Windows) or on the Linux host kernel | Opt-in only; the fail-closed isolation check with the runc version floor; `runsc` when listed; hardening flags; no mounts or socket |
| The host runc is below the floor | BLOCK `tool_error` (`isolation_failed`) on every `--detonate` | Update Docker. The floor can't be overridden |
| No local agent model for the agent phase | BLOCK `tool_error` (`coverage_incomplete`) | Configure `[detonate] agent` with a loopback Ollama. `doctor --docker` checks for it |
| A crash leaves resources behind | Clutter | Garbage-collect labeled resources older than one hour at startup |

**History, install and CI**

| Failure | Effect | Mitigation |
| --- | --- | --- |
| The database is locked or corrupt | No record | A warning; the verdict is unaffected; `--no-history` |
| Semgrep isn't on PATH under pipx or uv | Static fails | Resolve next to `sys.executable` (§9.1) |
| A typo in config | Wrong behavior | Strict validation → exit 2, naming the key |
| Anthropic is configured without the extra | `reader_unavailable` | The message names `pip install 'skill-warden[anthropic]'`; `doctor` checks for it |
| CI only checks for exit code 1 | ASK or BLOCK slips through | Docs say to treat any non-zero code as "not allowed" and to use `--format json` for logic |

---

## 18. Threat model and claims

**The adversary** is the skill's author, who controls every byte of the skill directory and its metadata. Their goal is to get a skill with a hidden payload installed: credential theft, persistence, memory poisoning or agent hijack. Failing that, they want Warden to say ALLOW.

| Attack on Warden | Mitigation |
| --- | --- |
| Prompt-inject the reader | No tools, schema-only output, prompt canary, strict parse, and the reader can only add evidence |
| Hide files from Semgrep | Explicit targets, a scanned-target check, the liveness canary, rules only from Warden |
| Unicode tricks | `Cf` characters stripped and recorded as a finding; NFKC normalization |
| Symlinks to host files | An intake error; `pack_skill` refuses escapes |
| Huge inputs, to cause a DoS or run up cost | Caps and timeouts |
| Claims of safety | Worth at most a medium finding, never decisive |
| Sandbox detection and time bombs in the jail | Probe, delay and profile-divergence findings, plus a lived-in home and clock skew. A known gap |
| Escaping or weakening the jail | A fail-closed isolation check before any skill bytes enter |
| Malformed input aimed at the scanner itself | Subprocess isolation, timeouts, fail-closed on any crash |
| Configuring the scanner through repository files | No implicit project config |

**Out of scope:**

- a compromised Warden installation;
- a malicious Semgrep release or LLM provider;
- kernel exploits against Docker;
- skills that are benign when scanned and fetch their payload later, which needs a runtime monitor, a different tool.

**What Skill Warden does not claim:**

- ALLOW doesn't mean safe. It means that no stage that ran found evidence, and the report lists which stages those were.
- The reader is a heuristic. It can be talked into silence, but not into ALLOW.
- The jail is a hardened container, not a VM. `--detonate` runs untrusted code on your machine.
- History detects naive edits only. It is not signed.
- Registry rule packs are not covered by the liveness check.
- A README, a frontmatter field or a marketplace `security.status` is never a clearance.

---

## 19. Roadmap (after the MVP)

1. **Content-pinned approvals.** `skill-warden approve RUN_ID --reason …` writes `skill-warden.lock` (the content SHA-256, the accepted rule IDs, who and when). CI fails when an installed skill's hash hasn't been approved. A human, recorded, content-pinned decision is the useful core of the hackathon's "user origin" memory idea.
2. **Signed verdicts and lockfile** (minisign, or Ed25519 through `cryptography`).
3. **More artifact types:** Claude hooks in `.claude/settings.json`, `.mcp.json`, Cursor rules, `AGENTS.md` and `CLAUDE.md`.
4. **Remote sources:** ClawHub `slug@version` and GitHub URLs. Download, hash and scan. Never trust an advertised hash or `security.status`.
5. **Detonation.** Python and Node scripts, TLS capture, the agent phase and `runsc` moved into the MVP (R18–R25). Deferred on purpose:
   - ASK for a canary read that matches the skill's declared purpose (a claim isn't evidence);
   - a fourth INCONCLUSIVE decision (incomplete coverage stays BLOCK `tool_error`);
   - ASK on timeout;
   - gVisor as the default on Docker Desktop. Firecracker and Kata need Linux KVM;
   - an offline package cache or read-only registry proxy, so that declared installs can succeed;
   - a provenance check against the linked source repository;
   - host eBPF observation, which on Docker Desktop would watch the VM, and under gVisor the Sentry;
   - Linux time namespaces, which need `CAP_SYS_ADMIN` in the jail;
   - symbolic or multi-path execution.
6. **Reader:** chunked review for large skills; an optional second model.
7. **Distribution:** a GitHub Action, a pre-commit hook, a Homebrew formula.
8. **Claude on Bedrock, Vertex and Foundry,** through the SDK's platform clients.

---

## 20. Facts checked (14 October 2026)

| Fact | How it was checked |
| --- | --- |
| Baseline: 169 tests pass (Docker 28.5.1, Semgrep 1.180.0, Python 3.14.7) | `PATH=.venv/bin:$PATH python -m pytest tests -q` |
| Semgrep exits 2, with `results: []` and an `errors[]` entry at `level: "error"`, on a rule parse error. It exits 7 for a missing config | Local runs, Semgrep 1.180.0, in a scratch directory |
| Explicit file targets are scanned even when the skill's `.semgrepignore` lists them. A directory target obeys that file and drops `SKILL.md` | Local runs |
| `paths.scanned` is present in the JSON output. `--disable-version-check` exists | Local run; `semgrep scan --help` |
| U+200B inside `MEMORY.md` defeats `skill-memory-file-persistence`. `./MEMORY.md` doesn't match the folded regex | Local runs |
| Ollama's OpenAI-compatible API supports `response_format` and `max_tokens`; doesn't document `max_completion_tokens`; doesn't support `tool_choice`; ignores the key locally; base URL `http://localhost:11434/v1/` | docs.ollama.com/api/openai-compatibility |
| Docker's `isolated` gateway mode needs `--internal` and assigns no bridge address. The docs don't say which version added it | docs.docker.com/engine/network/port-publishing |
| This Mac: Docker Engine 28.5.1 with runc 1.2.5, below the 1.2.8 / 1.3.3 floor. `docker diff` doesn't show writes inside tmpfs mounts (16 October 2026) | `docker version`; a local `--read-only` run with tmpfs at `/home/agent` and `/tmp` |
| The Semgrep CLI runs natively on Windows (November 2025 release; public beta from July 2025) | semgrep.dev blog: Community Edition Fall Release 2025 |
| Anthropic Messages API: use the official SDK; structured output through `output_config.format` with a JSON schema; sampling parameters rejected on current models; Opus 5.5 can't disable thinking; `stop_reason: "refusal"` with `stop_details`; the SDK retries 408, 409, 429 and 5xx (twice by default); `anthropic` 1.x is built on `httpx2`; refusal fallbacks via `fallbacks: "default"` and beta `server-side-fallback-2026-07-01` on `client.beta.messages.create`, with fallback runs marked by `fallback` content blocks and `usage.iterations` entries of type `fallback_message` | The Claude API reference bundled with Claude Code (model table cached 6 October 2026) |

Not verified; check during implementation:

- every preset except Ollama's;
- whether OpenAI rejects `tool_choice` sent without `tools` (moot once it's never sent);
- whether `skill-warden` is free on PyPI;
- the published major version of the `anthropic` SDK.
