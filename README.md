# CLI Contract Guard (Claude Code plugin)

[![ci](https://github.com/ultrathinker/cli-contract-guard/actions/workflows/ci.yml/badge.svg)](https://github.com/ultrathinker/cli-contract-guard/actions/workflows/ci.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A plugin for maintainers of small command-line tools. It treats your CLI's
public surface as a versioned **contract** so you can tell, before every
release, whether a change is breaking, compatible, or cosmetic.

A command-line tool has two audiences at once: humans at a terminal and
scripts in CI. Unit tests usually cover the business logic, so a
"cosmetic" tweak to `--json` output or an exit-code value silently breaks
someone else's automation and only gets noticed by users. CLI Contract
Guard exists so that does not happen.

## What it does

1. You author one `contract.json` for your CLI: every command, every flag,
   every positional argument, every exit code, the JSON schema (if any),
   and the stream routing.
2. You capture text snapshots yourself (a `--help`, a `--json` invocation,
   an error path) into `snapshots/<version>/<case>.txt`. The plugin does
   **not** run your binary.
3. Before each release, you ask the plugin to compare the new snapshots
   against the previous version. It classifies every change, weighs the
   verdict against your `stability.policy` and `stability.audiences`, and
   tells you which entries of `contract.json` need an update, plus a
   CHANGELOG entry you can paste.

## What it does not do

- It does not execute your binary. Snapshots are yours to capture (see
  the capture recipe in the `contract-init` skill).
- It does not auto-generate `contract.json` from your source code. The
  `contract-init` skill reads the README, `pyproject.toml`,
  `package.json`, or source files as ground truth when they exist, then
  asks you to confirm. When there is no source yet it runs a short
  interview.
- It does not commit, push, or open a PR. It produces a verdict and a
  suggested patch; the maintainer applies them.
- It does not pin a remote package or a runtime tool. Both scripts are
  pure Python 3 standard library; the validator and the snapshot
  classifier have no dependencies.
- The classifier's flag, JSON-key, and exit-code heuristics are
  best-effort. They are evidence, not the verdict; the contract-review
  skill applies the rules in
  `skills/contract-review/references/classification-rules.md` to decide
  breaking vs compatible vs cosmetic.

## Install

In Claude Code:

```
/plugin marketplace add ultrathinker/cli-contract-guard
/plugin install cli-contract-guard@cli-contract-guard
```

Then restart the session (or run `/reload-plugins`). To try it without
installing, load it from a working copy for one session:

```
claude --plugin-dir ./cli-contract-guard
```

The plugin uses no MCP servers and no hooks. It ships one slash command,
`/contract-snapshot-diff`, which only runs the bundled classifier script on
two files you name.

The two scripts in `scripts/` need a Python 3.9+ interpreter on `PATH`
either as `python3` or `py` (Windows Python launcher); if `python3`
is not available, fall back to `python` or `py -3`. They use only
the standard library.

## Use it

In your CLI's repository:

1. Ask the plugin to **initialize a contract** for your tool. It will
   read your README and source as ground truth, ask a few clarifying
   questions, and write `contract.json` next to your code.
2. Capture your first set of snapshots. The recipe lives in
   `skills/contract-init/SKILL.md`; the short form is to use the
   structured convention the classifier understands:

   ```
   $ mytool --help
   <help text>

   --- exit 0
   ```

   ...or the same with `--- stderr` between the help text and the
   `--- exit N` line.

3. After every change, capture new snapshots and ask the plugin to
   **review the diff**. It classifies each change as breaking,
   compatible, or cosmetic; reports whether the verdict is allowed
   under your `stability.policy`; suggests the matching update to
   `contract.json`; and produces a CHANGELOG bullet.

If you want a deterministic diff before the review, run:

```
/contract-snapshot-diff snapshots/1.0.0/help.txt snapshots/1.1.0/help.txt
```

## Layout

```
.claude-plugin/plugin.json   Plugin manifest
README.md                    This file
LICENSE                      MIT
skills/
  contract-init/             Bootstrap a contract.json (reads source, runs interview)
  contract-review/           Classify a snapshot diff; suggest contract updates
  contract-design/           Guidance for stable CLI design choices
commands/
  contract-snapshot-diff.md  Slash command for a deterministic diff
scripts/
  validate_contract.py       Validate a contract.json (pure stdlib)
  classify_snapshot_diff.py  Diff two snapshots (pure stdlib)
examples/demo-cli/           A tiny worked example: contract + two snapshot versions
tests/                       Synthetic-data tests, runnable with `python tests/run_tests.py`
```

## Data

The plugin reads your `contract.json` and the snapshot files you point
it at. It does not call out to any network service, does not read
environment secrets, and does not write outside the files you ask it to
update. Snapshots are treated as text: the scripts apply a few
heuristics (flag names, JSON keys, exit codes) to produce evidence for
the contract-review skill; the skills do the semantic classification.
Privacy: `PRIVACY.md`. Security reports: `SECURITY.md`.

## License

MIT. See `LICENSE`.
