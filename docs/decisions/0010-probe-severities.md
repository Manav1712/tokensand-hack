# 0010 — Probe severities

Date: 2026-10-19. Status: accepted.

## Context
Reading `/.dockerenv` or the cgroup files was high (BLOCK). Ordinary software reads them too: Node CLIs check for Docker, and Go and Java size themselves to the container. The `TracerPid` rule matched a file path that can't occur, so it never fired.

## Decision
- **Container tells** (`/.dockerenv`, `/run/.containerenv`, the cgroup files, DMI) give `sandbox_probe` at medium, which is ASK.
- **Weaker reads** (`mountinfo`, `cpuinfo`, `/proc/<pid>/status`) give `env_probe` at low.
- A probe next to behavior that is high on its own (a canary trip, egress, persistence, a profile divergence) is BLOCK through that finding.
- The `TracerPid`-in-path rule and its test are deleted.

## Consequences
- Sandbox-aware malware that then does nothing gets ASK, not BLOCK. That is honest, because it did nothing.
- The severities get tuned from the benign corpus (T3) once there is data.
