# 0009 — Per-command time limits that classify a cut-off

Date: 2026-10-19. Status: accepted.

## Context
One 300 s clock covered every phase. With four profiles of four phases at 60 s each, slow but harmless skills ran out of time and got BLOCK. Malware also stalls on purpose.

## Decision
Each command gets its own limit:
- install: 120 s;
- script invocation: 30 s;
- `SKILL.md` block: 30 s;
- agent turn: 60 s.

A command ends as soon as its process tree exits. The stage budget is the sum of the plan's limits plus 60 s, capped at 15 minutes and shown before the scan. Profiles run in parallel (v0.3).

A cut-off is classified from the strace tail, timed with `-T`:

| What the process was doing | Finding |
| --- | --- |
| More than half its limit asleep, or any sleep over 30 s | `delay` (high) |
| Busy with almost no syscalls | `stall_busy` (medium) |
| Still working | `command_timeout` (medium) |

Commands past the cap are `budget_exceeded` (medium).

## Consequences
- A slow, harmless skill is ASK, and the user can approve it.
- Padding a skill with slow commands buys an attacker ASK, never ALLOW.
- Warden's own global clock stays BLOCK `timeout`.
