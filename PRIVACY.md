# Privacy Policy

Last updated: 2026-09-30

cli-contract-guard runs on your machine. It has no telemetry and no accounts, makes no network requests and sends nothing to the author or to any third party.

## What the scripts do

- `validate_contract.py` reads the one `contract.json` you point it at, and `classify_snapshot_diff.py` reads the two snapshot files you point it at. Both print their result to your terminal.
- They write no files, start no other programs and make no network requests, and their own code reads no environment variables.

## What the skills and the command do

- The skills and the `/contract-snapshot-diff` command are instructions that Claude reads inside your own Claude Code session. They have Claude read files in your project (your README, `pyproject.toml`, `package.json`, `Cargo.toml` or source files, your `contract.json` and your snapshots) and run the two scripts above through `python3`, `python` or `py`.
- `contract-init` drafts a `contract.json` in your project, checks it with the validator and shows it to you. `contract-review` asks before it edits `contract.json`.
- `contract-init` also contains a shell recipe for capturing a snapshot of your own tool's output. It runs your tool, writes the output to temporary files, saves the snapshot under `snapshots/` and removes the temporary files it created. It is a suggestion for you to run; the skills and scripts never run your tool themselves.

## What is stored and shared

The plugin keeps no data of its own and shares nothing with the author or with any third party. The only files that appear are the ones you create or approve: `contract.json`, your snapshots and the recipe's temporary files.

## Claude

What Claude itself does with the content it handles in your session, including any snapshots it reads, is governed by the terms and privacy policy that apply to your Claude account, not by this plugin. Snapshots hold whatever your tool prints, so keep secrets out of them.

## Questions

Open an issue in this repository's GitHub issue tracker. Security reports: see `SECURITY.md`.
