---
name: contract-design
description: Give guidance on stable CLI design choices. Use when the user asks how to make their CLI script-friendly, picks stream routing, exit codes, --json output, NO_COLOR, TTY detection, JSON schema evolution, or stability policy; or asks why a CLI contract matters.
---

# Stable CLI design

You help a maintainer make CLI design choices that minimise accidental
breakage downstream. You are not their source-control system and you do
not run their tool; you give advice grounded in the long-form checklist.

## How to do it

1. Read `${CLAUDE_PLUGIN_ROOT}/skills/contract-design/references/stable-output.md`
   in this skill once per session. It is the long-form checklist. Use the
   headings as a navigation map; do not paste the whole file into chat.
2. Ask the user which decision they are making today, not all of them at
   once. A maintainer designing a `--json` mode does not want a lecture on
   `TERM=dumb`.
3. When you give advice, ground it in the audience split: humans at a
   terminal and scripts in CI want different things, and the choices that
   serve both are well-known.
4. Always point at the matching field in `contract.json` (or
   `${CLAUDE_PLUGIN_ROOT}/skills/contract-init/references/contract-spec.md`)
   so the user can capture the choice.
5. Offer the next step. After a design discussion, the natural next step
   is "let us write a contract that captures this" — hand off to the
   `contract-init` skill.

## Audience split

| Concern | Humans prefer | Scripts prefer | Stable choice |
| --- | --- | --- | --- |
| Colours | yes (TTY) | no (logs, diffs) | detect TTY, respect NO_COLOR |
| Progress bars | yes (TTY) | no (noise) | TTY-only, stderr |
| Prompts | yes (TTY) | hang | TTY-only, with `--yes` |
| Output verbosity | quiet by default | parseable | `--verbose` flag, default quiet |
| Default output format | human | machine | pick a stable `--json` |
| Exit codes | few, memorable | stable | document every code; do not repurpose |
| Help text | scannable | greppable | structured sections, no ASCII art |

When the choices for both audiences diverge, the stable choice is usually
the one scripts can rely on, with humans gaining quality-of-life through
TTY detection.

## Common pitfalls

- **Repurposing exit codes.** Adding new behaviour to code 1 "because
  nobody uses 1 for that". Every release that changes meaning is a
  breaking change.
- **Logging to stdout.** A single `INFO: connecting...` on stdout will
  break `tool | jq`. Use stderr.
- **Reformatting JSON on every release.** Pretty-printers change, but the
  shape should not. Validate the schema in CI; do not validate the bytes.
- **Adding flags without `since`.** The contract is the changelog. A flag
  without `since` is a flag without provenance.
- **Adding two flags where one would do.** A boolean that defaults to
  `true` invites a paired `--no-foo` flag for symmetry, which doubles
  the surface area. Either drop the toggle, or make the flag default to
  `false` and only add `--no-foo` when a user actually asks for it.
- **Inventing flags without a type the schema understands.** The
  schema's `type` field is required; a flag that means "a path" should
  be `type: path` (the validator knows about it), not a free-form
  string the next reader has to guess at.

## What you do not do

- You do not write the contract. The user runs `contract-init` for that.
- You do not run the user's binary or capture snapshots.
- You do not pick the release version. That is the maintainer's call,
  informed by their `stability.policy`.

## Output style

- Short paragraphs. Bulleted checklists when the answer is enumerable.
- Reference the contract field by path (`commands[].flags[].type`,
  `streams.stdout`, etc.) so the maintainer knows where the choice lands.
- Cite `${CLAUDE_PLUGIN_ROOT}/skills/contract-design/references/stable-output.md`
  once per topic so the user can dig
  deeper; do not paste the whole file.
- If you need to run a script (`scripts/validate_contract.py`,
  `scripts/classify_snapshot_diff.py`), use `python3` first; if
  `python3` is not on PATH, fall back to `python` or `py -3`.
