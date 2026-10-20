# 0011 — A Debian slim jail image

Date: 2026-10-19. Status: accepted.

## Context
The jail ran on Alpine (musl). This had three problems:
- `/etc/alpine-release` is a sandbox tell, because laptops and CI runners use glibc;
- many Python wheels don't install on musl, so declared installs fail differently than on the user's machine;
- libfaketime is unreliable on musl.

## Decision
The jail image is `debian:<release>-slim`, pinned by digest, with every package pinned to a version. The sink is trusted and may stay on a small base, also pinned.

## Consequences
- Only the image inside Docker changes. Nothing is installed on the user's computer.
- The first download is larger, and it is cached by a content-addressed tag.
