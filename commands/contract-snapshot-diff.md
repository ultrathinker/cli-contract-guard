---
description: Run the snapshot diff classifier on two files and print a structured report.
argument-hint: BEFORE AFTER [--json] [--context N]
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/classify_snapshot_diff.py:*), Bash(python ${CLAUDE_PLUGIN_ROOT}/scripts/classify_snapshot_diff.py:*), Bash(py -3 ${CLAUDE_PLUGIN_ROOT}/scripts/classify_snapshot_diff.py:*)
---

# /contract-snapshot-diff

Run the deterministic snapshot diff between two files and print a structured
report. The contract-review skill then turns the evidence into a verdict.

## Arguments

- `BEFORE` (required): path to the previous snapshot.
- `AFTER` (required): path to the next snapshot.
- `--json` (optional): emit JSON instead of the human-readable format.
- `--context N` (optional): context lines around each change
  (default 3). Negative values are an error.

## Behaviour

1. Resolve `BEFORE` and `AFTER` from `$ARGUMENTS` or ask the user.
2. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/classify_snapshot_diff.py`
   with the requested flags. If `python3` is not on PATH, fall back to
   `python` or `py -3`. Only this script is pre-approved; do not run
   anything else through this command.
3. Print the script's output. Do not re-classify; the deterministic
   evidence is the value here.
4. Offer to invoke the `contract-review` skill for a full verdict. Do
   not invoke it automatically; the user may just want the diff.

## Exit codes

The script mirrors POSIX `diff`:

- `0`: the two files are identical.
- `1`: a diff was produced (the normal case).
- `2`: a file could not be read or the arguments were invalid.

## Errors

- File not found: report which path is missing, then list any snapshots
  in nearby `snapshots/` directories as a hint.
- Files identical: the script prints `IDENTICAL: ...`; pass that message
  through.
- The classifier does not modify anything on disk; nothing to undo.

## A note on what this command does not do

Naming a contract field by JSON path (for example "`commands.list.exit_codes`
now references code 2") is the contract-review skill's job, not this
script's. This command is the deterministic diff; the verdict is a
separate step.
