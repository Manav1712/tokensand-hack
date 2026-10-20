# 0001 — Ship a local CLI with no hosted services

Date: 2026-10-14. Status: accepted.

## Context
The hackathon build depended on ClickHouse (Cloud or a container), AkashML, Akash, Guild, GitHub pull requests and minisign. Those were sponsor integrations. A developer who wants to vet one skill shouldn't need an account, a server or credits.

## Decision
Skill Warden ships as a Python CLI installed with `pipx` or `uv tool`:
- the verdict is a pure function, `policy.decide`;
- history is a SQLite file;
- output is text or JSON plus an exit code.

No service is needed by default. Network use happens only when the user picks a hosted LLM or Semgrep registry rules.

## Alternatives
- Keep ClickHouse as the store. Rejected: it is a server process for a single-user tool, and the tests needed Docker.
- Keep publishing through Guild and Akash. Rejected: those are hosted control planes that were never built.

## Consequences
- The verdict SQL becomes Python, and the 19 SQL test cases are ported (§12).
- Signing and shared verdicts move to the roadmap (§19).
- `scripts/export_demo_traces.py` stops working once ClickHouse goes. `demo/` still builds from its committed data.
