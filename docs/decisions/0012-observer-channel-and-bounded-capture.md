# 0012 — A separate observer channel, and bounded capture

Date: 2026-10-19. Status: accepted.

## Context
- The hackathon jail ran strace without `-o`, so the trace shared stderr with the skill. A skill could print fake trace lines, including `<... resumed>` fragments, and corrupt the parser to hide a real `openat`.
- All jail output was read with unbounded `capture_output`, so a skill that flooded its output could exhaust host memory.

## Decision
- strace writes with `-o` to `/run/warden`, a root-owned 0700 tmpfs that the skill's user can't touch. The host reads it as root after each command.
- The skill's stdout and stderr are captured separately and only searched for canary values (`canary_output`).
- A missing or cut-short trace is `observer_attack` (high).
- Every read from the jail goes through a bounded reader with a 64 MiB cap per stream. Past the cap, the result is `observation_truncated` (high).

## Consequences
- The adversarial tests `forge-trace` and `flood-stdout` guard both properties.
- The isolation check allows exactly three tmpfs mounts: `/tmp`, `/home/agent` and `/run/warden`.
