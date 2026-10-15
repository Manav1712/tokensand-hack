# Skill Warden architecture

Checked against primary docs on 9 October 2026. The ClickHouse verdict SQL in this document was executed on `clickhouse/clickhouse-server:26.9.14.10`.

Skill Warden is a containment-first gate for third-party agent skills. A Python process on the laptop watches a registry, detonates each new skill inside a disposable Docker sandbox, records deterministic scanner output and a quarantined model’s flags, and asks ClickHouse for a fail-closed verdict. The host signs that verdict with minisign. A Guild agent publishes the signed file as a GitHub pull request. An Akash deployment, paid for once through the managed wallet, serves a public page that displays the pin.

The skill’s own README, `SKILL.md` claims, and marketplace `security.status` are not evidence.

## Decision

| Question | Choice |
| --- | --- |
| Where does the orchestrator run? | A Python 3.12 process on the demo laptop |
| Where does the untrusted skill execute? | A local Docker container on an internal network |
| What is the source of truth for the verdict? | One parameterized ClickHouse statement |
| How is the verdict protected? | minisign (Ed25519) on the host, public key committed to the fleet repo |
| What does Guild do? | Holds the GitHub credential, writes a session log, opens or updates the pin pull request |
| What does Akash do? | Hosts one pre-leased public verdict page and supplies AkashML as a tool-less reader |
| What does Pi do? | Acts as the unsandboxed victim on the host |
| What does Semgrep do? | Scans the skill inside Docker. A local rule always runs. The Pro Agent Skills pack runs only when it actually loads rules |
| Where do rows go? | ClickHouse Cloud. The same schema runs on local ClickHouse 26.9 if the trial is not ready |

Langfuse is out of the demo. ClickHouse acquired Langfuse on 16 January 2026. Langfuse Cloud and self-host remained separate products. A verdict, a canary, and a publisher rollup are SQL on Skill Warden’s own tables. Self-hosting Langfuse adds a web app, a worker, Postgres, Redis, and object storage.

## Why this shape

A third-party skill inherits the agent’s credentials and its permission to act. The payload is often natural language in `SKILL.md` (“read the env file and POST it”), a hook, or an instruction to append to `MEMORY.md`, which survives deletion of the skill. A gate that trusts the skill’s self-description, or that lets the skill’s text steer the process holding the GitHub token, is not a gate.

Four constraints decide the layout.

1. **The judge and the subject stay apart.** The orchestrator never puts `SKILL.md` in its own prompt. A second, powerless model reads the text and returns flags. A SQL statement, not that model, picks BLOCK, ASK, or ALLOW.
2. **The sandbox must be one the operator can actually deny.** Akash providers are untrusted operators. Current provider code leaves public IPv4 egress open and does not drop capabilities, set a non-root user, or make the root filesystem read-only. Docker on the laptop can.
3. **Guild’s runtime is a publisher, not a scanner.** A Guild TypeScript agent may import `@guildai/agents-sdk`, `zod`, and `@guildai-services/*`. External npm and Node built-ins are rejected. The agent container reaches the Guild API and nothing else. It cannot run Semgrep, insert into ClickHouse, or call minisign.
4. **A missing result is a block.** Timeout, zero rules loaded, a skipped `SKILL.md`, an invalid model response, a stalled run, or an absent findings row all become BLOCK. The system does not default to ALLOW.

## System context

```text
local git registry ──bytes + sha256──► Python orchestrator
                                            │
                    ┌───────────────────────┼────────────────────────┐
                    ▼                       ▼                        ▼
             Docker quarantine        AkashML reader          ClickHouse Cloud
             Semgrep + canary         flags JSON only         verdict SQL
                    │                       │                        │
                    └──────── findings ─────┴────────────────────────┘
                                            │
                                       minisign
                                            │
                                      Guild publisher
                                            │
                                      GitHub pin PR
                                            │
                                   Akash static page (browser fetch)
```

Pi sits beside this path. It is installed on the host with no sandbox, loads the fixture skill, and shows the canary leaving the machine. Pi does not scan, sign, or publish.

## Components

### Python orchestrator

One process. Libraries: `httpx` for ClawHub, the Guild API, and the Akash Console API; `clickhouse-connect` for inserts and the verdict query; the `openai` SDK pointed at AkashML or Ollama. Docker, Semgrep, and minisign are invoked as subprocesses. PyGithub is unnecessary. `gh` is an acceptable fallback for the same GitHub REST calls.

The process owns the loop:

1. Poll the registry.
2. Download bytes and recompute `sha256`.
3. Check the budget breaker.
4. Stage the skill into a scratch directory and start the sandbox.
5. Read scanner stdout and canary logs as data.
6. Call the reader with tools disabled.
7. Insert rows.
8. Run the verdict SQL.
9. Sign the canonical JSON.
10. Hand the signed document to Guild.
11. Tear the sandbox down in `finally`.

Secrets that live only in this process: the minisign secret key, the ClickHouse password, the AkashML key, the Akash Console API key, the Guild API trigger key, and, on the fallback path, the GitHub fine-grained PAT. None of these are mounted into the sandbox or sent to the reader.

### Registry

**Primary demo source: a local git repository of skill versions.** A fixture can be published on stage. Each version is a directory whose identity is publisher, name, version, and the sha256 of the fetched bytes. The orchestrator computes that hash. It does not accept a hash advertised by the package.

**Optional live source: ClawHub’s public read API.** Base URL `https://clawhub.ai`. Anonymous reads work. Writes need `Authorization: Bearer clh_...`. Documented limit is 3000 reads per minute per IP. Useful routes:

```text
GET /api/v1/skills?limit=100&sort=updated
GET /api/v1/skills/{slug}
GET /api/v1/skills/{slug}/versions?limit=20
GET /api/v1/skills/{slug}/versions/{version}
GET /api/v1/skills/{slug}/file?path=SKILL.md&version={version}
GET /api/v1/download?slug={slug}&version={version}
```

`sort=updated` is required to see a new version of an existing skill. Version detail includes per-file `sha256`. `security.status` and `security.sha256hash` are scan claims. On a live sample, `security.status` was `clean` while scanner `skillspector` was `suspicious`, and `security.sha256hash` pointed at a VirusTotal artifact rather than the file bytes. Recompute the hash from the zip or file bytes. `GET /api/v1/download` may return a zip, or a JSON `public-github` handoff for current GitHub-backed skills. Treat a handoff as “fetch the bytes from the URL it names, then hash them,” not as a clean bill of health.

skills.sh is a poor poller for this hackathon. `GET https://skills.sh/api/v1/skills` returned `401 authentication_required` and asked for a Vercel OIDC bearer token.

### Artifact being judged

The demo artifact is an Agent Skills directory, the on-disk shape shared by Claude, Pi, and OpenClaw, and the shape Semgrep’s skill rules target:

```text
skill-name/
├── SKILL.md          # required YAML frontmatter + markdown body
├── scripts/          # optional
├── references/       # optional
└── assets/           # optional
```

Required frontmatter is `name` (must match the directory name) and `description`. At startup a host typically loads only those two fields. The body loads when the skill is selected. Scripts can run without their source entering the model context, which is why the sandbox has to see the files on disk.

The same scanner accepts other paths. They are adapters, not separate products.

| Host | Paths |
| --- | --- |
| Claude | `SKILL.md`, `.claude/settings.json` hooks, `.mcp.json`, `CLAUDE.md`, `AGENTS.md`, `.claude/rules/*.md` |
| Cursor | `.cursor/rules/*.mdc`, legacy `.cursorrules`, `AGENTS.md`, `.cursor/mcp.json` |
| OpenClaw | `SKILL.md` plus `metadata.openclaw` (`requires.env`, `requires.bins`, `install`) |
| Pi | `SKILL.md` inside a package `skills/` directory, plus `extensions/*.ts` |

`MEMORY.md` is not in the skill package. Claude loads project memory from `~/.claude/projects/<project>/memory/MEMORY.md` (first 200 lines or 25 KB every session). A skill that says “append this to MEMORY.md” is a persistence payload aimed at that file. The fixture describes that instruction. The scanner does not perform it.

### Fleet memory

The fleet host keeps its own memory across sessions. This store does not decide which skills are safe. The scan still does that. The store is what stops a saved sentence from becoming a standing order.

Two files, both owned by the host:

* **Index.** One short file. Each memory is a single line: a short title, who wrote it, when it was written, and where the full note lives. This is the only memory loaded at the start of a session.
* **Notes.** One file per memory, holding the detail. A note stays on disk until the agent asks the host to open that one file. Other notes stay out.

A session starts with a table of contents. If no title matters, no note is opened and the session pays only for the index. Opening a note is a deliberate step, the same as opening any other file.

The host, not the model, stamps each line when it is written. The stamp is one of three origins:

| Origin | Meaning | What it may do |
| --- | --- | --- |
| User | The person said to remember it | Guide later work, including actions |
| Agent | The agent derived it from its own work in a trusted session | Guide later work, including actions |
| Outside | It arrived from a skill, a fetched page, a tool result, or any other text the agent did not author | Be read as information. It cannot authorize sending data, changing settings, or treating a skill as pre-approved |

A user note or a fresh user confirmation is required for those actions. If the agent summarizes or rewrites a note, the new note inherits the weakest origin in what it was built from. Weakest means least authority: outside is weaker than agent, and agent is weaker than user. An outside sentence rewritten in the agent’s voice stays outside. The skill cannot set or change the stamp, including by asking the agent to rephrase the sentence.

The index ceiling is 200 lines or 25 KB, whichever comes first. The host refuses a write that would pass it. Lines past the ceiling are not kept and ignored. Near the ceiling the agent shortens the index on purpose: merge duplicates, drop stale lines, and leave detail in a note that is not loaded at startup. Dropping an index line does not delete the note. The note remains on disk and can be found by search. It stops costing every session.

A skill can still ask the agent to save a sentence. If the agent does, that sentence is an outside note. Its index line is one short row, so it cannot fill the session. A later session that opens it still treats it as outside. This store does not shrink a note that was opened. A single opened note can still be long. The savings come from not opening every note at the start of every session.

Pi 1.0 shipped on 1 October 2026 (`@earendil-works/pi-coding-agent`). Pi has no built-in sandbox. Project trust only gates whether project settings and extensions load. Packages run with the user’s permissions. That is why Pi is the victim in the demo and not the place the scan runs.

### Detonation jail

The jail is the center of the system. It does not merely block the skill. It lets the skill believe the theft worked, and it records the attempt. A skill that posts a planted key to a URL and gets `200 {"ok":true}` has shown its plan. The nonce inside that key is the evidence.

Runtime, checked 9 October 2026 for a Mac with Docker Desktop: hardened runc inside the Docker VM. Kata and Firecracker need Linux KVM. gVisor is an unsupported install into the Docker Desktop VM. Apple `container` on macOS 26 gives a VM per container and drops `docker diff` and shared-network sidecars. The laptop jail stays on Docker. An escape lands in the Docker VM, not on macOS, only if the host home, the repo, and the Docker socket are not mounted.

Walls on the untrusted container: `--cap-drop ALL`, keep only `SETUID` and `SETGID` so the entrypoint can drop to uid 10001, `--security-opt no-new-privileges`, `--read-only`, `--pids-limit`, `--memory` equal to `--memory-swap`, sized tmpfs for `/tmp` and the fake home, image pinned by digest, per-phase `timeout`. The skill is copied in with a tar stream. Symlinks are not followed. A link that resolves outside the skill root is refused. Nothing from the host is bind-mounted.

Network: one `--internal` bridge, no route to the public internet and no route to the Docker Desktop engine API. A trusted sink container is the DNS server. It answers every name with its own address and logs every query. A catch-all HTTP and TLS server on the sink, with a per-run CA installed in the jail image, answers `200` and writes the request body. `HTTP_PROXY` and `HTTPS_PROXY` point at the sink. A tcpdump sidecar uses `--network container:<jail>` so the pcap is not in the skill’s mount namespace. Traffic to a hard-coded IP has no route. `strace` still records the destination and port.

What runs inside, in two phases, each with its own timeout:

1. **Scripts.** Every file in `scripts/` and every fenced command in `SKILL.md`, with `--help`, with no args, and with the args the skill documents. No model. This catches a payload that is a script.
2. **Agent.** A small Python loop with tools `read_file`, `write_file`, `list_dir`, and `bash`, driven by a local Ollama model reached only through a reverse proxy on the sink. The task is the skill’s own description, which is benign. Pi in `--mode json` is an optional second actor in the same jail. Pi has no sandbox of its own. That is why it runs here and nowhere else.

Observation comes from three places, so a skill that kills one watcher is seen by the others:

| Watcher | Where it runs | What it records |
| --- | --- | --- |
| `strace -f` as root, JSONL on container stdout | Inside, above uid 10001 | exec argv, file opens including missing paths, `connect` destination |
| `docker diff` and `docker logs` | Docker daemon | Files created or changed, the strace stream |
| DNS log, HTTP bodies, pcap | Sink and tcpdump sidecar | Lookups, request bodies, packets |

The fake home holds a real-format AWS key (`AKIA`), a `ghp_` token, an ed25519 SSH key, a Claude-style key, a Pi config, `.env`, `.npmrc`, and `MEMORY.md`. Each secret contains a per-run nonce. `MEMORY.md` names where the “prod” keys live. Secrets live in files. Environment reads are not syscalls, so a decoy env var is only a supplement. The nonce is searched raw, base64, hex, and URL-encoded.

A second run keeps the same fake home, moves the clock forward with `libfaketime`, and changes hostname, MAC, and machine-id. Sandbox probes are findings: `/.dockerenv`, `/proc/1/cgroup`, `TracerPid`, a long `sleep`, writes to shell rc files, cron, `.git/hooks`, or other skills.

The host writes a manifest: skill tree hash, image digest, and the sha256 of the strace log, pcap, DNS log, HTTP log, and diff. minisign signs that manifest. ClickHouse stores the hashes. The jail does not choose BLOCK or ALLOW.

Akash still does not run this jail. A backend pointed at Akash must refuse to detonate a skill.

### Semgrep

Semgrep runs inside the scanner container as a CLI subprocess, not as an MCP server the model drives. `semgrep mcp` and `uvx semgrep-mcp` exist. For this demo they add a tool-using model that has already read the skill. Call `semgrep scan` from Python instead.

```python
import subprocess
r = subprocess.run(
    ["semgrep", "scan", "--metrics=off", "--json",
     "--scan-unknown-extensions", "--timeout", "20",
     "--config", "/opt/warden/rules/memory.yaml", skill_md],
    capture_output=True, text=True, timeout=30,
)
```

`--config` points only at Warden-owned files. A skill can ship `.semgrep.yml` that hides matches. Hash the rules directory at process start.

**Markdown caveat.** Semgrep’s `generic` language matches `.generic` files. `.md` is an unknown extension and is skipped on a directory walk. `--scan-unknown-extensions` applies to files named on the command line. Pass every text file explicitly. If the JSON result lists `SKILL.md` under skipped paths, the scan failed.

**Rulesets, fetched without a token on 9 October 2026:**

| Ruleset | Rules | Unauthenticated `https://semgrep.dev/c/p/<name>` |
| --- | --- | --- |
| `p/agent-skills` | 117, all `team_tier` / `pro_rules` | `rules: []` |
| `p/shadow-ai-pro` | 186, all Pro | `rules: []` |
| `p/shadow-ai` | 145 | YAML for the public subset |
| `p/ai-best-practices` | 27, all public | YAML |

A May 2026 Semgrep blog said 122 Agent Skills rules. The registry on 9 October 2026 listed 117, under `semgrep-rules-proprietary/.../paid/skills/`. These five exist and are Pro:

- `skills.behavioral.skill-indirect-prompt-injection.skill-indirect-prompt-injection`
- `skills.hooks.skill-hook-credential-exfiltration.skill-hook-credential-exfiltration`
- `skills.hooks.skill-hook-bash-reverse-shell.skill-hook-bash-reverse-shell`
- `skills.behavioral.skill-excessive-autonomy.skill-excessive-autonomy`
- `skills.behavioral.skill-system-prompt-extraction.skill-system-prompt-extraction`

There is also `skills.behavioral.skill-memory-poisoning.skill-memory-poisoning`. Rule bodies were not readable without a token.

`semgrep scan` itself does not require an account. `p/agent-skills` does. An empty `rules: []` is a failed scan. Record `rules_loaded`. If the Pro pack was requested and the count is 0, insert a policy finding with severity `error`, which the verdict SQL turns into BLOCK.

Always run the local rule below. It is the no-token stand-in for the memory-poisoning rule. Severity `ERROR` is the old name for `HIGH`.

```yaml
rules:
  - id: skill-memory-file-persistence
    languages: [generic]
    severity: ERROR
    message: >-
      Instruction to write or append an agent memory file (MEMORY.md or
      CLAUDE.md). That text is loaded into later sessions.
    metadata:
      category: security
      confidence: MEDIUM
    pattern-regex: >-
      (?i)(write|append|save|persist|update).{0,80}
      (MEMORY\.md|CLAUDE\.md|agent memory)
```

`p/ai-best-practices` is an optional no-token supplement. It includes generic hook and settings rules (`hooks-dns-exfiltration-generic`, `hooks-wget-pipe-bash-generic`, `claude-settings-bypass-permissions-generic`, `mcp-tool-poisoning-generic`, `ai-config-hidden-unicode-generic`). It does not replace the Pro skill pack. `p/shadow-ai` finds LLM SDK usage in application code. Skip it. Semgrep Supply Chain and the malicious-package firewall are a local MITM proxy plus a platform product. Skip them in four hours.

Before scanning, copy the tree, NFKC-normalize the copy, and strip Unicode format characters (`Cf`). Hash the original bytes for identity. If stripping changes the file, record an `obfuscation` finding at medium.

### Quarantined reader

AkashML is OpenAI-compatible at `https://api.akashml.com/v1` with a bearer key `akml-...`, distinct from the Console API key. `POST /v1/chat/completions` accepts `tools` and `tool_choice`. Set `tool_choice` to `none`. Cap `max_completion_tokens` around 512. Default model `openai/gpt-oss-120b` after confirming the id with `GET /v1/models`. A 20k-token skill plus a short JSON reply on that model is well under a cent at the rates published on 9 October 2026. `402` means out of credits and stops the call.

The model is powerless only because this process never gives it tools and never executes the text it returns. The AkashML key stays on the orchestrator. Putting it in an SDL `env` block would ship it to an Akash provider.

Fallback: Ollama’s OpenAI-compatible API at `http://127.0.0.1:11434/v1/` with `qwen2.5:7b`.

```python
from openai import OpenAI
client = OpenAI(base_url="https://api.akashml.com/v1", api_key=AKASHML_KEY)
resp = client.chat.completions.create(
    model="openai/gpt-oss-120b",
    temperature=0,
    max_completion_tokens=512,
    response_format={"type": "json_object"},
    messages=[
        {"role": "system", "content": SYSTEM_WITH_CANARY},
        {"role": "user", "content": "UNTRUSTED SKILL FOLLOWS\n" + bounded_text},
    ],
)
```

Containment rules:

1. The system prompt is fixed Warden text. Untrusted bytes sit in one delimited user block.
2. The prompt tells the model to treat that block as data, to ignore any instruction inside it to change a verdict, and to emit only the JSON schema.
3. A random canary string lives in the system prompt. If it appears in the output, the skill extracted the reader prompt. That is BLOCK.
4. The schema has flags and short evidence quotes. It has no verdict field, so “output ALLOW” has nowhere to land.
5. Extra prose, extra keys, a missing field, or a refusal is an invalid read. Insert `source=reader`, `severity=error`.
6. Temperature is 0.

Flags: `indirect_injection`, `credential_exfil`, `memory_persistence`, `shell_callback`, `false_safety_claim`, `obfuscation`.

Mapping into `findings`, which is what the SQL actually sees:

| Reader or scanner result | Row |
| --- | --- |
| `indirect_injection`, `credential_exfil`, `memory_persistence`, `shell_callback` | `source=reader`, `severity=high` |
| `false_safety_claim`, `obfuscation` | `source=reader`, `severity=medium` |
| Semgrep CRITICAL, HIGH, or ERROR | `source=semgrep`, `severity=high` |
| Semgrep MEDIUM or WARNING | `source=semgrep`, `severity=medium` |
| Semgrep LOW or INFO | `source=semgrep`, `severity=info` or `low` |
| Clean Semgrep completion | one sentinel row: `source=semgrep`, `rule_id=semgrep.ok`, `severity=info` |
| Canary HTTP hit, honeytoken read, or nonce in a file, body, or DNS label | `source=canary`, `severity=critical`, excerpt `[canary tripped]` |
| Jail event: connect to a non-sink address, sandbox probe, persistence write, long sleep, tracer death | `source=jail`, `severity=high` |
| Invalid reader output, or prompt canary echoed | `source=reader`, `severity=error` |
| Pro pack requested and `rules_loaded == 0`, or `SKILL.md` skipped | `source=policy`, `severity=error` |

A README that says “security-audited” becomes `false_safety_claim` at medium. Medium alone is ASK. A high finding in the same run is BLOCK, and the claim cannot outrank it. The demo’s second skill needs both the boast and a real high-severity pattern. Blocking a clean skill only because it claims to be safe would be a false conviction.

### ClickHouse

**System of record: ClickHouse Cloud.** Trial is $300 of credits for 30 days, no card to start. The SQL endpoint is the service on HTTPS port 8443 (native TLS 9440). Plaintext is refused. Start signup at the beginning of the day. The Cloud quickstart currently places a new org on the Scale tier (3 replicas, 4 vCPU / 16 GiB). Prefer Basic, or Scale with idle-to-zero and a small replica, so an idle weekend does not burn the credits. Storage still bills. Query API Endpoints are a saved-SELECT wrapper and are the wrong tool for inserts.

**Fallback: local Docker**, same DDL, HTTP port 8123. This is what the SQL below was executed against.

```bash
docker run -d --name ch --ulimit nofile=262144:262144 \
  -p 8123:8123 \
  -e CLICKHOUSE_DB=skill_warden \
  -e CLICKHOUSE_USER=admin \
  -e CLICKHOUSE_PASSWORD="$CLICKHOUSE_PASSWORD" \
  -e CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT=1 \
  clickhouse/clickhouse-server:26.9
```

`CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT=1` is required or `CREATE USER` returns `ACCESS_DENIED`. With no password, the `default` user has no network access.

```python
import os
import clickhouse_connect

client = clickhouse_connect.get_client(
    host=os.environ["CLICKHOUSE_HOST"],
    port=int(os.environ.get("CLICKHOUSE_PORT", "8443")),
    username=os.environ["CLICKHOUSE_USERNAME"],
    password=os.environ["CLICKHOUSE_PASSWORD"],
    database=os.environ.get("CLICKHOUSE_DATABASE", "skill_warden"),
    secure=os.environ.get("CLICKHOUSE_SECURE", "true").lower() == "true",
)
```

Local Docker uses `HOST=localhost`, `PORT=8123`, `SECURE=false`, `USERNAME=scanner`.

Inserts use `async_insert=1` and `wait_for_async_insert=1`. On 26.9 both already default to 1. Set them anyway. `wait_for_async_insert=0` can return success before the flush, with errors only in server logs. Prefer `client.insert` with an explicit column list. A bad enum value rejects the whole batch and writes zero rows. Retry an identical batch so block deduplication can collapse it. Local plain MergeTree needs `non_replicated_deduplication_window = 1000`. Cloud replicated tables already keep a dedup log. Dedup matches the whole block. A second batch with a different row is a second write.

Environment: `CLICKHOUSE_HOST`, `CLICKHOUSE_PORT`, `CLICKHOUSE_USERNAME`, `CLICKHOUSE_PASSWORD`, `CLICKHOUSE_DATABASE`, `CLICKHOUSE_SECURE`.

#### Schema

`inserted_at` and `signed_at` default to `now64(3, 'UTC')` on the server. Order and the stall check use those columns so laptop and Cloud clocks cannot disagree. `excerpt` and `response_json` are redacted. Column TTL blanks them after 14 days at merge time, not instantly. Row TTL is 180 days except `verdicts`, which has none. TTL does not stop a `SELECT` from seeing expired values until the merge.

```sql
CREATE DATABASE IF NOT EXISTS skill_warden;

CREATE TABLE skill_warden.skills
(
    publisher LowCardinality(String),
    name String,
    version String,
    content_hash String,
    fetched_at DateTime64(3, 'UTC'),
    source_url String,
    inserted_at DateTime64(3, 'UTC') DEFAULT now64(3, 'UTC')
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(fetched_at)
ORDER BY (publisher, name, content_hash, fetched_at)
TTL fetched_at + INTERVAL 180 DAY
SETTINGS non_replicated_deduplication_window = 1000;

CREATE TABLE skill_warden.scan_runs
(
    run_id UUID,
    skill_hash String,
    started_at DateTime64(3, 'UTC'),
    finished_at Nullable(DateTime64(3, 'UTC')),
    backend Enum8('local' = 1, 'akash' = 2),
    status Enum8('running' = 1, 'completed' = 2, 'timeout' = 3, 'error' = 4),
    budget_cents UInt32,
    inserted_at DateTime64(3, 'UTC') DEFAULT now64(3, 'UTC')
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(started_at)
ORDER BY (started_at, run_id)
TTL started_at + INTERVAL 180 DAY
SETTINGS non_replicated_deduplication_window = 1000;

CREATE TABLE skill_warden.findings
(
    run_id UUID,
    source Enum8('semgrep' = 1, 'reader' = 2, 'canary' = 3, 'policy' = 4, 'jail' = 5),
    rule_id LowCardinality(String),
    severity Enum8('info' = 1, 'low' = 2, 'medium' = 3, 'high' = 4, 'critical' = 5, 'error' = 6),
    file String,
    evidence_hash String,
    excerpt String TTL observed_at + INTERVAL 14 DAY,
    indicator String DEFAULT '',
    observed_at DateTime64(3, 'UTC') DEFAULT now64(3, 'UTC'),
    inserted_at DateTime64(3, 'UTC') DEFAULT now64(3, 'UTC')
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (run_id, source, rule_id, evidence_hash)
TTL observed_at + INTERVAL 180 DAY
SETTINGS non_replicated_deduplication_window = 1000;

CREATE TABLE skill_warden.model_io
(
    run_id UUID,
    model LowCardinality(String),
    prompt_hash String,
    response_hash String,
    response_json String TTL inserted_at + INTERVAL 14 DAY,
    injection_flag UInt8,
    inserted_at DateTime64(3, 'UTC') DEFAULT now64(3, 'UTC')
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(inserted_at)
ORDER BY (run_id, prompt_hash)
TTL inserted_at + INTERVAL 180 DAY
SETTINGS non_replicated_deduplication_window = 1000;

CREATE TABLE skill_warden.verdicts
(
    run_id UUID,
    decision Enum8('BLOCK' = 1, 'ASK' = 2, 'ALLOW' = 3),
    reason_code LowCardinality(String),
    signer LowCardinality(String),
    signature String,
    published_url String DEFAULT '',
    pr_url String DEFAULT '',
    immutable UInt8 DEFAULT 1,
    payload_hash String,
    prev_hash String DEFAULT '',
    signed_at DateTime64(3, 'UTC') DEFAULT now64(3, 'UTC')
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(signed_at)
ORDER BY (signed_at, run_id)
SETTINGS non_replicated_deduplication_window = 1000;

CREATE TABLE skill_warden.budget_events
(
    event_id UUID,
    run_id UUID,
    occurred_at DateTime64(3, 'UTC'),
    kind LowCardinality(String),
    cents Int64,
    inserted_at DateTime64(3, 'UTC') DEFAULT now64(3, 'UTC')
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(occurred_at)
ORDER BY (occurred_at, run_id, event_id)
TTL occurred_at + INTERVAL 180 DAY
SETTINGS non_replicated_deduplication_window = 1000;
```

`scan_runs.budget_cents` is the cap for that run. `budget_events.cents` is spend. `indicator` is a redacted host, used by the exfil query. `immutable` is a label. `payload_hash` is the application’s hash of the canonical evidence and decision. `prev_hash` is the previous verdict’s `payload_hash`, computed by a single writer. `backend` stays `local` for detonation. The `akash` enum value exists so a mistaken skill lease is visible in the table. The Akash page deploy is not a scan run.

App user, created by `admin`:

```sql
CREATE USER IF NOT EXISTS scanner IDENTIFIED WITH sha256_password BY 'choose-a-real-secret';
GRANT SELECT, INSERT ON skill_warden.* TO scanner;
GRANT ALTER UPDATE(status, finished_at) ON skill_warden.scan_runs TO scanner;
```

`scanner` can `SELECT` and `INSERT`. It can also `UPDATE` `scan_runs.status` and `scan_runs.finished_at`, so a finished run stays one row. `ALTER DELETE`, `DROP TABLE`, and `TRUNCATE` return `ACCESS_DENIED`. On Cloud, `GRANT ALL` is not accepted. Grant `SELECT` and `INSERT` explicitly, plus that column update.

#### Verdict SQL

Bind `run_id`. First match wins. Executed cases on 26.9.14 included a missing run, a young `running` row, a stalled `running` row, `timeout`, a completed run with no findings, high, canary, reader `error`, a policy row with no Semgrep row, medium, the clean Semgrep sentinel, critical, a completed run with null `finished_at`, two rows for one `run_id`, Semgrep `error`, and low-only.

```sql
WITH
    runs AS (
        SELECT
            count() AS run_count,
            any(status) AS run_status,
            any(finished_at) AS finished_at,
            any(inserted_at) AS inserted_at
        FROM skill_warden.scan_runs
        WHERE run_id = {run_id:UUID}
    ),
    f AS (
        SELECT
            count() AS finding_rows,
            countIf(source = 'semgrep') AS semgrep_rows,
            countIf(source = 'canary') AS canary_rows,
            countIf(source = 'reader' AND severity = 'error') AS reader_error_rows,
            countIf(severity = 'error' AND source != 'reader') AS other_error_rows,
            countIf(severity IN ('high', 'critical')) AS high_rows,
            countIf(severity = 'medium') AS medium_rows
        FROM skill_warden.findings
        WHERE run_id = {run_id:UUID}
    )
SELECT
    {run_id:UUID} AS run_id,
    multiIf(
        run_count = 0, 'BLOCK',
        run_count != 1, 'BLOCK',
        run_status = 'timeout', 'BLOCK',
        run_status = 'running' AND inserted_at < now64(3, 'UTC') - INTERVAL 10 MINUTE, 'BLOCK',
        run_status != 'completed' OR finished_at IS NULL, 'BLOCK',
        finding_rows = 0, 'BLOCK',
        canary_rows > 0, 'BLOCK',
        reader_error_rows > 0, 'BLOCK',
        other_error_rows > 0, 'BLOCK',
        high_rows > 0, 'BLOCK',
        semgrep_rows = 0, 'BLOCK',
        medium_rows > 0, 'ASK',
        'ALLOW'
    ) AS decision,
    multiIf(
        run_count = 0, 'missing_run',
        run_count != 1, 'duplicate_run',
        run_status = 'timeout', 'timeout',
        run_status = 'running' AND inserted_at < now64(3, 'UTC') - INTERVAL 10 MINUTE, 'timeout',
        run_status != 'completed' OR finished_at IS NULL, 'not_finished',
        finding_rows = 0, 'no_findings',
        canary_rows > 0, 'canary',
        reader_error_rows > 0, 'reader_error',
        other_error_rows > 0, 'tool_error',
        high_rows > 0, 'high_finding',
        semgrep_rows = 0, 'semgrep_missing',
        medium_rows > 0, 'medium_only',
        'clean'
    ) AS reason_code
FROM runs
CROSS JOIN f;
```

```python
client.query(sql, parameters={"run_id": run_id})
```

Placeholders are `{name:Type}`. An unbound `{run_id:UUID}` errors with `UNKNOWN_QUERY_PARAMETER`. Do not concatenate skill text into SQL. A `SELECT` that contains a literal is written to `query_log` in full. On 26.9.14 the JSONEachRow insert body itself was not in `query_log`.

Low and info findings do not become ASK. They become ALLOW only when the run completed, Semgrep produced a row, and nothing medium or worse is present. The 10-minute stall threshold is a hackathon constant, not a server default. A young `running` row is BLOCK via `not_finished` until it completes. That is correct: an in-flight scan is not an allow.

#### Fleet queries

Top flagged publishers, last 30 days:

```sql
SELECT
    s.publisher,
    uniqExact(v.run_id) AS blocked_runs
FROM skill_warden.verdicts AS v
INNER JOIN skill_warden.scan_runs AS r ON v.run_id = r.run_id
INNER JOIN
(
    SELECT content_hash, argMax(publisher, fetched_at) AS publisher
    FROM skill_warden.skills
    GROUP BY content_hash
) AS s ON r.skill_hash = s.content_hash
WHERE v.decision = 'BLOCK'
  AND v.signed_at >= now() - INTERVAL 30 DAY
GROUP BY s.publisher
ORDER BY blocked_runs DESC
LIMIT 20;
```

Exfil hosts first seen in the last day and absent from the prior 30:

```sql
SELECT
    indicator,
    min(observed_at) AS first_seen,
    uniqExact(run_id) AS runs
FROM skill_warden.findings
WHERE indicator != ''
  AND observed_at >= now() - INTERVAL 1 DAY
  AND indicator NOT IN
  (
      SELECT indicator
      FROM skill_warden.findings
      WHERE indicator != ''
        AND observed_at < now() - INTERVAL 1 DAY
        AND observed_at >= now() - INTERVAL 30 DAY
  )
GROUP BY indicator
ORDER BY first_seen DESC
LIMIT 50;
```

Verdicts by hour, last 7 days:

```sql
SELECT
    toStartOfHour(signed_at) AS hour,
    decision,
    count() AS n
FROM skill_warden.verdicts
WHERE signed_at >= now() - INTERVAL 7 DAY
GROUP BY hour, decision
ORDER BY hour, decision;
```

Repeated memory-file patterns:

```sql
SELECT
    rule_id,
    evidence_hash,
    count() AS hits,
    uniqExact(run_id) AS runs
FROM skill_warden.findings
WHERE file LIKE '%MEMORY.md'
GROUP BY rule_id, evidence_hash
HAVING hits > 1
ORDER BY hits DESC
LIMIT 20;
```

#### Trust boundary

ClickHouse is an audit store. It is not a ledger. MergeTree rewrites rows into new parts during merges. The `immutable` column does not stop that. What can be claimed honestly:

- The scanner connects as `scanner`, which was denied `ALTER DELETE`, `DROP`, and `TRUNCATE`.
- Each verdict stores `payload_hash` and a signature produced outside ClickHouse.
- The signing key is not on the database host and not in the agent.
- `prev_hash` links to the previous `payload_hash` if one process signs at a time. Two signers can read the same tail and fork the chain.
- ClickHouse does not check the signature. Anyone with the Cloud console, the `admin` password, or the disk can update, delete, or restore parts. Verification in Python fails when they do. Publish the signature with the verdict so a reader can check it without trusting the database operator.

### Signing

minisign, local Ed25519, no KMS and no network. Default signatures are prehashed (`ed25519(Blake2b-512)`). The trusted comment is covered by the signature. The untrusted comment is not. Leave the secret key password-encrypted. `-W` stores it without a password. Do not use `-W`.

```bash
minisign -G -s ~/.minisign/skill-warden.key -p ./minisign.pub
minisign -S -s ~/.minisign/skill-warden.key -m verdict.json \
  -t "skill-warden publisher=alice name=foo version=1.2.0"
minisign -V -m verdict.json -p ./minisign.pub
```

Commit `minisign.pub` to the fleet repo before the demo. The signed file is the canonical verdict JSON, not the skill body. Fields: publisher, name, version, `content_sha256`, decision, reason code, timestamp. The trusted comment repeats publisher, name, and version so a swapped file fails verification. Guild cannot verify the signature. It has no libsodium and cannot import a verifier. Verification is `minisign -V` on a machine that already has the public key.

Cosign keyless (Fulcio, Rekor, OIDC) needs a network and an identity provider. It is the wrong default for a four-hour local demo.

### Guild publisher

Guild is a hosted control plane at `app.guild.ai` and `api.guild.ai`. New accounts are a free trial. Managed LLM calls draw a token balance. A deterministic agent that never calls `task.llm` should not spend tokens. That is an inference from the docs, not a billing guarantee.

Use `GUILD_TYPESCRIPT` with a deterministic `agent()`. Input is the already-signed verdict. Tools, via `pick`:

- `github_repos_get_content`
- `github_repos_create_or_update_file_contents`
- `github_pulls_list`
- `github_pulls_create`

The agent writes `verdict.json` and the `.minisig` onto branch `pins/skill-warden`. If a pull request from that head is already open, a new commit updates it. If none is open, it calls `github_pulls_create`. It does not fetch the skill, does not read `SKILL.md` as evidence, and does not receive ClickHouse credentials.

Pre-create `pins/skill-warden` once. The Contents API `branch` field names an existing branch. The published GitHub tool list does not include `POST /repos/{owner}/{repo}/git/refs`. Do not bet the demo on Guild creating the branch.

Wake the agent with an API trigger. The trigger key is created in the web UI. Account API keys cannot create that trigger type.

```bash
curl -X POST "https://api.guild.ai/v1/workspaces/$OWNER/$WORKSPACE/sessions" \
  -u "$API_KEY_ID:$API_KEY_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"session_type":"api_trigger","agent_input":{"text":"<signed verdict JSON>"}}'
```

Poll `GET /v1/sessions/{session_id}` until `root_task.status` is `DONE`, `ERROR`, or `INTERRUPTED`. Events: `GET /v1/sessions/{session_id}/events`. Default sort is newest first. The trigger key can read and write any session in that workspace. The trigger body is the public verdict. It is the wrong place for a secret. API-trigger sessions have no acting user, so a per-user spend budget does not apply.

Credential handling:

- The agent never receives the GitHub secret. Guild’s proxy checks policy, then adds auth. GitHub is a GitHub App. Guild mints short-lived installation tokens.
- A new credential starts allow-all. A request no rule allows is denied only after that allow-all policy is removed. `DENY` beats `ALLOW`.
- Delete allow-all. Allow only the four operations above, scoped to the fleet repo. Deny `pulls_merge`, `repos_delete`, and `repos_delete_file`.
- Policy operation names in the docs are unprefixed (`pulls_create`). Tool names are prefixed (`github_pulls_create`). Confirm which string the live matcher uses before the demo.
- Disconnecting a credential denies later tool calls, including calls from sessions already running. It does not close a pull request that already opened. There is no feature named “tripwire.”

Do not enable `experimental_fetch` or a custom REST integration on this agent. Both give it outbound HTTP. Custom integration base URLs block loopback, private ranges, and internal DNS, so Guild also cannot post to a laptop ClickHouse.

Do not use `GOOSE` or `OPENCLAW` agent types as the sandbox. Coding-container setup has network access, and `experimental_coding_create` accepts caller-supplied `env`. That is a bad place to run an untrusted skill. Runtime then drops general egress.

Session events and the organization audit log are the evidence trail. The audit log is admin-only, read-only, CSV-exportable, and described as tamper-evident. The docs do not show a hash chain. A personal-account trial may only have session history. Confirm that at signup.

Schedule triggers are too coarse for a live demo (`HOURLY` or five-field `CRON`, and they run inside Guild). The Python loop is the poller. Guild is invoked only when there is a signed verdict to publish.

**Fallback if Guild is not ready:** a fine-grained PAT on the host, one repository, Contents read and write, Pull requests read and write. Metadata read is included automatically. Do not grant Administration, Secrets, Actions, or Workflows. Expire the token the same day. Create the branch ref with `POST /git/refs` from the current `main` SHA, then `PUT` the file contents, then `POST /repos/{owner}/{repo}/pulls` with API version `2026-03-10`. The sandbox still never sees this token.

### Akash page and payment

Console API: `https://console-api.akash.network`, header `x-api-key`. There is no official Python SDK. Use `httpx`. Signup is email, Google, or GitHub. New accounts get $1 of trial credit for 30 days, no card. Trial deployments auto-close after 24 hours. Credits are USD. Console converts them to ACT. The key cannot be exported. Auto Top-Up, which charges a card, stays off.

Deploy loop for the verdict page:

| Step | Call |
| --- | --- |
| Create | `POST /v1/deployments` with `{ "data": { "sdl": "<yaml string>", "runtimeLimitHours": 6 } }` |
| Bids | `GET /v1/bids?dseq=`. Empty `data` means still waiting |
| Lease | `POST /v1/leases` with `{ "leases": [{ "dseq", "gseq", "oseq", "provider" }] }`. Omit `manifest`. Console sends it |
| Close | `DELETE /v1/deployments/{dseq}` |

Bids often start in 30–60 seconds. That is not time-to-ready. Image pull sits on top. `runtimeLimitHours` is a whole-hour backstop from lease start and cannot be lowered later. It does not replace `DELETE`. If bids are empty at 60 seconds, `DELETE` the dseq and show a local copy of the page.

SDL price `amount` is the maximum in `uact` per block. 1 ACT = 1,000,000 uact. Blocks are about 6 seconds. `amount: 100` caps the lease near $1.44/day. Start at 100. Raise it only after a no-bid response. You pay the accepted bid, which must be at or below the ceiling. Console holds on the order of two days of the deployment’s cost in escrow and returns the unused part on close.

```yaml
version: "2.0"
services:
  web:
    image: nginx:1.27.3
    expose:
      - port: 80
        as: 80
        to:
          - global: true
profiles:
  compute:
    web:
      resources:
        cpu:
          units: 0.5
        memory:
          size: 512Mi
        storage:
          size: 512Mi
  placement:
    akash:
      pricing:
        web:
          denom: uact
          amount: 100
deployment:
  web:
    akash:
      profile: web
      count: 1
```

The page is static HTML that fetches `verdict.json` from the raw URL of `pins/skill-warden` on the public fleet repo. Updating the verdict does not require a new lease. The repo has to be public for the browser fetch. The HTML is pre-built. It does not contain canaries, skill bodies, or API keys.

SDL requires at least one `expose.to.global: true`, so this container is reachable from the internet. That is acceptable because it serves a public file. Do not request a persistent volume. Do not set `params.permissions.read`. Do not put secrets in `env`. Provider log WebSockets (`POST /v1/create-jwt-token`, then a self-signed provider host) are out of the demo.

`GET /v1/balances` exists in current Console source and returns raw chain units. Divide by 1e6 for ACT. The route’s auth behavior was not fully verified. Use the Console UI or `akt console wallet balance` for the number you trust in the demo.

Akash is a bad place to detonate a skill, in detail:

- The provider receives the manifest, env, and image, and can exec the pod.
- Workload defaults: `privileged: false`, `allowPrivilegeEscalation: false`, `runAsNonRoot: false`. Capabilities are not dropped. The root filesystem is not read-only. SDL has no fields for those.
- With network policy enabled, egress still allows all public IPv4 except RFC1918, plus in-namespace traffic and cluster DNS. Policies are optional and the provider decides. IPv6 denial was not confirmed.
- Closing the deployment deletes the namespace on an honest provider. A dishonest provider can keep the disk.
- Confidential compute hides memory from the provider, which is the wrong direction for a sandbox you need to observe.

### Budget breaker

The breaker lives in the Python process. Console will keep funding a deployment you forget to close.

- Auto Top-Up off. Prepaid balance is the ceiling ($1 trial, or about $5 on a card).
- At most one Akash deployment and one local container.
- Local wall clock 45–60 seconds, then `docker kill`.
- Akash: `runtimeLimitHours` set, and `DELETE` in `finally`, including bid timeout and lease `502`.
- SDL ceiling stays at 100 uact/block unless bids never arrive.
- AkashML: one completion per skill, `tool_choice` none, token cap set, stop on `402`.
- A `KILL` file checked before each run.

```python
import time
from pathlib import Path

class Breaker:
    def __init__(self, max_usd=5.0, max_jobs=1, max_seconds=60):
        self.max_usd = max_usd
        self.max_jobs = max_jobs
        self.max_seconds = max_seconds
        self.spent = 0.0
        self.active = 0
        self.kill = Path("./KILL")

    def enter(self, est_usd: float):
        if self.kill.exists():
            raise RuntimeError("kill switch")
        if self.active >= self.max_jobs or self.spent + est_usd > self.max_usd:
            raise RuntimeError("budget")
        self.active += 1
        self.spent += est_usd
        return time.monotonic()

    def leave(self):
        self.active -= 1
```

Estimate the Akash page at the SDL ceiling times the hour backstop. Estimate an AkashML call from `/v1/models` prices times the token cap. Local Docker costs $0 in this counter. The process wall clock is the other stop.

### Pi

Pi runs on the host for the attack half of the demo. Install the fixture into a stock Pi instance and show the fake canary reach a local webhook. The fixture uses `example.invalid`, `EXAMPLE_TOKEN`, and a `FAKE-CANARY` comment. It is not a live shell and not a real endpoint.

After a BLOCK, Pi may format the pin diff from the verdict JSON. That is optional. Guild can write the same file. If Pi is used for the diff, it sees the verdict only. It does not receive the GitHub token, and it does not run inside the scanner container.

Third-party extensions such as `security-guard` do substring checks on tool calls. They illustrate the gap. They are not the fleet gate.

### Demo fixtures

All of these are obviously fake. No live shell, no real collector.

1. **Indirect injection.** `SKILL.md` presents itself as a date formatter. An HTML comment or a fenced example tells the agent to ignore the user task and follow the comment.
2. **Hook exfil shape.** A settings or skill-hook command string reads an environment variable and sends it to `https://example.invalid/collect` with `EXAMPLE_TOKEN`.
3. **Memory rewrite.** `SKILL.md` tells the agent to append a line to the project `MEMORY.md` so later sessions treat the skill as pre-approved. If that sentence is saved anyway, fleet memory stamps it outside. The stamp is not a clearance. The scan still returns BLOCK when the instruction matches.
4. **Reverse-shell shape.** `scripts/sync.sh` contains a TCP client aimed at `example.invalid`, with `FAKE-CANARY` on the previous line. The script is not executable and is not run.
5. **Contradicting README.** `README.md` says the package is independently audited. `SKILL.md` is fixture 1 or 3. Expected result: BLOCK, with the README claim stored as `false_safety_claim`.
6. **Clean control.** `SKILL.md` plus `scripts/format_date.py` that only formats a date. Expected result: ALLOW, via the `semgrep.ok` sentinel and an empty flag list.

### Demo sequence

1. **Attack.** Publish the poisoned skill to the local registry. Install it into stock Pi. Show the canary hit the local webhook.
2. **Defend.** Start the orchestrator. It provisions nothing on Akash for this scan. Docker starts, Semgrep fires, the reader flags the injection, ClickHouse returns BLOCK.
3. **Publish.** The signed verdict lands in a GitHub pull request. The Akash page, already leased, shows it. `minisign -V` succeeds against the committed public key. The Guild session log shows the publish and nothing else.
4. **Money shot.** Run the second skill, whose README says it is verified safe. The high finding still wins.

Floor if a sponsor stalls: local Pi, the local Semgrep rule, a BLOCK row in ClickHouse, and one real GitHub pull request.

## End-to-end sequence

1. The poller lists the local registry, or ClawHub `sort=updated`.
2. It downloads the skill bytes and computes `content_sha256`. A mismatch with a previously recorded hash for that version is BLOCK (`tool_error` via a policy row, or a dedicated finding at `error`).
3. `Breaker.enter` runs. A `KILL` file or a budget breach refuses the job.
4. A `scan_runs` row is inserted with `status=running`, `backend=local`.
5. The tree is copied to `./scratch/skill`. A normalized copy is made for scanning.
6. Compose starts `scanner` and `canary` on the internal network.
7. The scanner runs Semgrep on an explicit file list and prints JSON findings to stdout. The canary logs any POST.
8. On timeout, the run is updated to `status=timeout` and the containers are removed. The verdict SQL returns BLOCK. The reader is not called.
9. Otherwise the host calls AkashML with the normalized text. Invalid JSON or an echoed canary becomes a reader error row.
10. Findings and `model_io` are inserted. A clean Semgrep run still inserts `semgrep.ok`. Excerpts are redacted. `indicator` stores a redacted host when one was parsed from a finding, never a raw token.
11. `scan_runs` is updated to `completed` with `finished_at` set.
12. The verdict SQL runs.
13. The host builds canonical JSON, signs it, and inserts `verdicts` with `payload_hash`, `signature`, and `prev_hash`.
14. The host POSTs the signed JSON to the Guild API trigger and polls until the session finishes. It then updates `pr_url`.
15. Containers are removed in `finally`. `Breaker.leave` runs. The Akash deployment is not created or destroyed on this path.

## Four-hour build order

### 0:00–0:40 — accounts, keys, images

- Start the ClickHouse Cloud trial immediately. Apply the schema. If signup stalls, run the local 26.9 container and the same DDL.
- Create `scanner`. Confirm `ALTER DELETE` is denied.
- `minisign -G`. Commit `minisign.pub` to the fleet repo.
- Pre-create `pins/skill-warden`.
- Guild: deterministic agent, API trigger, one GitHub credential, allow-all removed, four operations allowed.
- Fine-grained PAT on the host as fallback. One repo. Expires the same day.
- `docker compose build` the scanner with Semgrep installed.
- Akash: API key, Auto Top-Up off, nginx SDL at `amount: 100`, `runtimeLimitHours: 6`. Lease it before judges arrive.
- AkashML key on the host, or `ollama pull qwen2.5:7b`.
- Write the poisoned fixture and the clean control.

### 0:40–1:30 — detonation

- Confirm the internal network, the read-only mount, and the non-root user.
- Run the known-bad fixture. Expect a high finding or a canary hit.
- Run the clean control. Expect `semgrep.ok` and no canary hit.
- If a Semgrep token exists, request `p/agent-skills` and assert `rules_loaded > 0`. With no token, do not request the pack.

### 1:30–2:30 — orchestrator

- Registry poll, hash, breaker, Compose, reader, inserts, verdict SQL.
- Redaction check: a canary token string does not appear in `findings.excerpt` or `model_io.response_json`.

### 2:30–3:20 — publish

- Sign, insert the verdict, POST to Guild, confirm the pull request.
- If Guild stalls, publish with the host PAT.
- Point the Akash page at the raw pin file and reload it.

### 3:20–4:00 — rehearsal

- Attack, defend, and the “audited” skill, twice, with images already pulled and the Akash lease already up.

## Failure modes

### Control plane

| Failure | What happens | Mitigation |
| --- | --- | --- |
| Allow-all GitHub policy left in place | The same integration can merge and delete | Delete allow-all. Allow four operations. Deny merge and delete |
| Secret in `task.env` or the trigger body | The value appears in session logs | Trigger body is the public verdict. GitHub auth stays in the credential proxy |
| Sandbox can read the Guild trigger key | It can start publishes and read other sessions | Scrub the sandbox environment. No home mount |
| Guild used as the scanner | Imports and internet are rejected | Scanning stays in Python and Docker |
| `experimental_fetch` or a custom integration enabled | The publisher gains outbound HTTP | Do not enable them |
| Coding container used as the sandbox | Setup has network and accepts `env` | Do not run the skill there |
| Session events polled newest-first | A naive poll looks empty or reversed | Page with `from_id` |
| Personal trial has no org audit log | Only session history exists | Treat the session log as the trail. Confirm at signup |
| Two publishes call `pulls_create` | Validation fails because the PR exists | Commit onto the open PR |

### Quarantine

| Failure | What happens | Mitigation |
| --- | --- | --- |
| Skill detonated on Akash | Untrusted operator, public IPv4 egress, no cap drop, no read-only root | Docker on the laptop |
| Provider keeps the disk after close | Chain close does not wipe a malicious host | Do not send secrets or the real skill there |
| Docker bridge reaches the host | Internal networks can still hit `0.0.0.0` listeners, especially on Docker Desktop | `gateway_mode: isolated`. Bind host services to `127.0.0.1` |
| Repo, home, or Docker socket mounted | The scan reads the signing key | Mount only `./scratch/skill:ro` |
| `uvx` or an image pull at scan time | Closed network fails the scan, or the demo stalls | Bake Semgrep in. Pull the image beforehand |
| Canary placed in Akash SDL `env` | The provider can read it and fake a trip | Canaries exist only inside Docker |
| Container survives the orchestrator | The skill keeps running | `timeout` in the command, `docker kill` in `finally` |

### Detection

| Failure | What happens | Mitigation |
| --- | --- | --- |
| `p/agent-skills` with no token | Zero rules, and the scan looks clean | `rules_loaded == 0` is BLOCK. Always run the local YAML |
| Semgrep skips `SKILL.md` | The payload is never opened | Explicit file list and `--scan-unknown-extensions`. A skip is BLOCK |
| Skill ships `.semgrep.yml` | Matches are suppressed | `--config` only from Warden’s directory. Hash it at startup |
| Prompt injection into the reader | The skill asks for an empty flag list or ALLOW | Separate process, no tools, flags-only schema, prompt canary, invalid JSON is BLOCK. SQL decides |
| README says the skill is audited | A self-description is treated as evidence | The claim is a medium finding. A high finding in the same run is BLOCK |
| Novel prose or Unicode obfuscation | No regex hit | NFKC plus strip `Cf`. Reader is the second stage. A changed file is at least ASK |
| Scanner timeout | No result | Subprocess timeout. `scan_runs.status=timeout`. SQL returns BLOCK |
| Model refusal | An apology instead of JSON | Invalid read is BLOCK |

### Data plane

| Failure | What happens | Mitigation |
| --- | --- | --- |
| Cloud signup stalls | No remote SQL endpoint | Local ClickHouse, same schema. Start the trial first |
| Scale tier burns the $300 | Idle replicas stay awake | Basic, or Scale with idle-to-zero and a small replica |
| Insert returns an error, or the client dies after commit | Partial uncertainty about the row | Retry the same batch. Check `written_rows`. Keep `wait_for_async_insert=1` |
| `wait_for_async_insert=0` | HTTP 200 with a later flush failure | Leave wait on |
| Schema drift (`severity='nope'`) | The whole batch is rejected | Explicit column list. Leave `input_format_skip_unknown_fields` off |
| Canary or skill body stored or concatenated into SQL | Secret in a column or in `query_log` | Redact before insert. Bind `{run_id:UUID}` |
| Clock skew between laptop and Cloud | Ordering and TTL drift | Server defaults `now64(3, 'UTC')` for `inserted_at` and `signed_at` |
| Same `run_id` inserted twice as different batches | Verdict returns `duplicate_run` and BLOCK | One findings batch per run. A rescan is a new `run_id` |
| Admin edits a verdict in the SQL console | The row changes | The signature check fails. That is the detection |

### Spend

| Failure | What happens | Mitigation |
| --- | --- | --- |
| Deployment left open | Escrow burns. Auto Top-Up charges the card | Auto Top-Up off. `finally` plus `runtimeLimitHours` |
| New lease per skill | 30–60s to first bid, longer to ready | One pre-leased page |
| No bids by 60s | Order is open and funded | `DELETE`, show the local page |
| `502 provider_unreachable` | No lease | Next bid, then `DELETE` |
| `502 manifest_not_delivered` | Lease exists and is billing | Retry `POST /v1/leases` once, then `DELETE` |
| Price ceiling too low | No bids | Raise `amount` once |
| Price ceiling too high | Escrow locks a large slice of the $1 trial | Stay at 100 uact/block |
| AkashML key in the sandbox, or tools enabled | The skill spends credits, or the completion is executed | Key on the host. `tool_choice` none. Parse JSON. Never exec it |
| Orchestrator loops | Repeated scans and model calls | One active job, USD ceiling, 60s clock, `KILL` file |

### Publish

| Failure | What happens | Mitigation |
| --- | --- | --- |
| Guild cannot verify minisign | No libsodium, no extra npm | Host signs. Fleet repo already has `minisign.pub` |
| Credential disconnected after the PR opens | Later tool calls stop. The PR stays | Revoke means “no further publishes.” Closing the PR is separate |
| Akash page fetch fails | Repo is private, or the pin path moved | Public repo. Fixed raw URL. Local page as backup |
| Signer and publisher are the same host | A compromised laptop can sign a lie | The sandbox is not that host. The key is not in the container |

## Open questions

These do not block the floor demo. They block a specific integration if the answer is no.

1. Which permissions does the Guild GitHub App request, and can it be installed on one personal repository?
2. Does the live contents-update tool accept `branch`, and is ref creation missing from the tool schema?
3. Does a personal-account trial have the organization audit log, and can the deterministic publisher run without buying tokens?
4. Which digest does `GET /api/v1/resolve?slug=&hash=` expect?
5. For a GitHub-backed ClawHub skill, does `GET /api/v1/skills/{slug}/file` still return bytes when download returns a handoff?
6. Does the ClickHouse Cloud trial restrict client IPs?
7. Which string does Guild’s credential-policy matcher use, `pulls_create` or `github_pulls_create`?
8. Is a Semgrep App token available in the room?

## What this design refuses to claim

- That ClickHouse is tamper-proof.
- That an Akash provider is a malware sandbox.
- That `security.status: clean`, a README, or a model’s prose is a clearance.
- That disconnecting a Guild credential undoes a pull request.
- That an empty Semgrep result is a clean skill.
- That Guild session logs are a public hash-chained proof. The docs say entries cannot be edited or deleted. They do not show a hash chain.
