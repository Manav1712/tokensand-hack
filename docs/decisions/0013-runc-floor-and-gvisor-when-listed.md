# 0013 — A runc floor, and gVisor when it's available

Date: 2026-10-16. Status: accepted.

## Context
Three runc container escapes (CVE-2025-31133, CVE-2025-52565 and CVE-2025-52881) were fixed in runc 1.2.8, 1.3.3 and 1.4.0-rc.3. gVisor is the stronger runtime, but it is unsupported on Docker Desktop for Mac. On 16 October 2026 the operator's Mac reported runc 1.2.5.

## Decision
- Use `runsc` when `docker info` lists it. Otherwise use hardened runc at or above the floor.
- Before any skill bytes enter the jail, check three things:
  - the host: the runtime and its version;
  - the container: no privileged mode, no host namespaces, only the planned tmpfs mounts, no `docker.sock`;
  - the inside, from a probe run as uid 10001: capabilities, seccomp, `NoNewPrivs`, a read-only root, a non-root uid, and no direct route out.
- Any failure is `isolation_failed` (error), BLOCK.
- The floor can't be overridden.

## Consequences
- `--detonate` is BLOCK on this Mac until Docker Desktop is updated (gate G5).
- CI runs the docker suite under runc on every PR and under runsc nightly.
