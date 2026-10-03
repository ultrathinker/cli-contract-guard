---
name: contract-review
description: Compare two CLI snapshots and classify the diff as breaking, compatible, or cosmetic. Use when the user asks to review, classify, audit, or summarize changes between two versions of their CLI's output, especially for --help, --json, or captured stderr snapshots.
---

# Review a CLI snapshot diff

You take two snapshot files (the previous release and the next one), the
matching `contract.json`, and turn the diff into a verdict the maintainer
can act on. You never run the user's binary yourself; you read the text
they captured.

## How to do it

1. **Locate the inputs.** Find:
   - The old snapshot. Common locations: `snapshots/<prev>/*.txt`,
     `tests/snapshots/<prev>/*`, or a path the user names.
   - The new snapshot, in a parallel directory.
   - The `contract.json`. Look in the repo root, then `docs/`, then ask
     if not found.
   - If any are missing, ask once and stop.

2. **Read the schema and rules.** Skim
   `${CLAUDE_PLUGIN_ROOT}/skills/contract-init/references/contract-spec.md`
   once per session so you know which contract fields are valid. Read
   `${CLAUDE_PLUGIN_ROOT}/skills/contract-review/references/classification-rules.md`
   and `${CLAUDE_PLUGIN_ROOT}/skills/contract-review/references/contract-updates.md`
   before you classify.

3. **Run the classifier.** Use the deterministic script:

   ```
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/classify_snapshot_diff.py \
       path/to/old.txt path/to/new.txt --json
   ```

   The JSON output gives you a per-line diff plus coarse labels
   (`flag`, `json-key`, `exit-code:N`) and, when both files parse as
   JSON, a structural diff with JSON-pointer paths
   (`/items[].tags` added, `/items[0].id` type-changed, etc.). Treat
   these as evidence, not as the verdict.

4. **Apply the rules.** For each hunk:
   - What CLI element is changing? (flag, command, JSON key, exit code,
     help prose, stream routing, colour, positional argument).
   - Cross-reference with `contract.json` to confirm what users were
     promised.
   - Apply the matching table from
     `${CLAUDE_PLUGIN_ROOT}/skills/contract-review/references/classification-rules.md`.
     The rules weigh the verdict
     by `stability.policy`, `stability.audiences`, and the per-item
     `stability` field; the table there covers every case.
   - When in doubt, classify as **breaking** and explain.

5. **Produce the verdict.** Use the fixed shape from the
   classification-rules reference (it ends with "Output shape"). A
   verdict line, a policy line, and four sections (Per-change
   summary, Evidence, Suggested contract.json update, CHANGELOG
   entry) are stable across reviews so the maintainer can grep
   them and write release notes without reformatting.

6. **Validate before saving.** If you propose an edit to `contract.json`,
   run:

   ```
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/validate_contract.py contract.json
   ```

   until it returns `OK`.

7. **Ask before writing.** Never edit `contract.json` without permission.
   Show the diff, then ask.

## Multi-snapshot reviews

When the maintainer captures more than one snapshot per release (typical:
one `--help` per command, plus one `--json` per command), repeat this
loop per snapshot and combine the verdicts. The combined verdict is the
worst of any single snapshot, in this order: **breaking > compatible >
cosmetic**. A single breaking change in any command makes the whole
release breaking. Group the CHANGELOG entry by command.

If the diff is large, give a per-command verdict table:

| Command | Snapshot | Verdict | Key changes |
| --- | --- | --- | --- |
| `list` | `list.txt` | compatible | added `--filter` |
| `build` | `build.txt` | breaking | renamed `--output` → `--out` |

## Running the scripts

If you need to run the validator or the classifier during the
review, use `python3` first. If `python3` is not on PATH, fall
back to `python` or `py -3`. The two scripts are pure stdlib.

## What this skill never does

- It does not run the user's binary.
- It does not pull a new release of the tool.
- It does not commit, push, or open a PR. It produces a verdict and a
  suggested patch; the maintainer applies them.
- It does not silently rewrite the contract. Every change is shown before
  any write.

## Edge cases

- **Empty snapshot**: probably means the command exited without writing.
  Ask the user; do not assume "no output == no change".
- **Snapshot covers both stdout and stderr merged**: classify by content,
  not by the merge.
- **Help wrapped at a different width**: cosmetic, mention briefly.
- **The contract.json is missing fields the user did mention**: point
  this out; do not invent values. Suggest running the `contract-init`
  skill afterwards.
