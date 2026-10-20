# 0005 — Content hash version 2 covers every file

Date: 2026-10-19. Status: accepted.

## Context
The hackathon `content_hash` ignored a top-level file named `HASH`. A skill could keep changing instructions in that file ("read HASH and follow it") without changing its identity, and any approval bound to the hash would still apply.

## Decision
`content_hash_v2` covers every regular file, `HASH` and dotfiles included. Each entry is length-prefixed and holds the relative POSIX path, a mode byte for the execute bit, the length and the bytes, sorted by path. Reports and history record `hash_version: 2`. Approvals accept only version 2.

## Alternatives
Keep v1 so that hashes stay comparable with the hackathon runs. Rejected: nothing depends on that comparison.

## Consequences
- Old hashes no longer match the new ones.
- A Hypothesis property checks that any change to a byte, a path or an execute bit changes the hash.
