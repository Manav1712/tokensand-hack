# 0006 — Read what the agent reads

Date: 2026-10-19. Status: accepted.

## Context
An attacker can exploit any difference between what Warden reads and what the agent loads. Two such differences were found:
- frontmatter read by a simple line parser, while agents use a real YAML loader;
- paths that differ only in letter case. `SKILL.md` and `skill.md` can both exist on Linux, but on a case-insensitive file system the agent sees only one of them.

## Decision
- **Frontmatter is read twice**, with `yaml.safe_load` (PyYAML, a declared dependency) and with the line parser, and the results are compared (§8 step 6):
  - disagreement on `name` or `description` → medium;
  - disagreement on install commands → high;
  - an unsupported construct in a compared field → medium;
  - a YAML parse failure → high.
- Detonation uses the YAML reading.
- **Two paths that differ only in letter case** give `case_collision` (high), and both files are scanned.

## Consequences
- Both findings are properties of the skill, so the user can approve them.
- Warden never guesses which reading the agent will use.
