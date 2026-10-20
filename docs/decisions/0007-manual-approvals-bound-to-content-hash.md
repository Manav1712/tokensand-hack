# 0007 — Manual approvals bound to one content hash

Date: 2026-10-19. Status: accepted.

## Context
A BLOCK with no way out makes users uninstall a security tool. An honest AWS-helper skill reads `~/.aws/credentials`, trips the canary, and would be blocked forever.

## Decision
`skill-warden approve RUN_ID --reason …` records a decision in a per-user `approvals.toml`, bound to one version 2 content hash and the rule IDs it accepts. The policy treats those findings as covered (§12.1). There are three levels:

| Findings in the run | What `approve` needs |
| --- | --- |
| Ordinary findings | `--reason` |
| A canary read (`honeytoken`) | Also `--accept honeytoken` |
| A canary that went out (`canary_egress`, `canary_argv`, `canary_file`, `canary_output`) | Also `--accept` naming each rule, plus an interactive confirmation, with no flag to skip it |

Errors and missing stages are never approvable.

## Consequences
- Changing any byte, or new evidence the approval doesn't list, brings the block back.
- Approvals are never read from the scanned directory.
- The report always shows `ALLOW (approved …)`.
- Approvals that teams share and sign are on the roadmap.
