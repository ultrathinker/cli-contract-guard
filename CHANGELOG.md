# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0]

First public release.

### Added
- Three skills (`contract-init`, `contract-review`, `contract-design`) and the `/contract-snapshot-diff` command for
  keeping a versioned contract of a command-line tool's public surface (commands, flags, exit codes, JSON output,
  stream routing) and classifying snapshot diffs as breaking, compatible or cosmetic.
- Two dependency-free Python scripts: `scripts/validate_contract.py` (contract validation) and
  `scripts/classify_snapshot_diff.py` (a deterministic snapshot diff with classification evidence).
- A worked example (`examples/demo-cli`) and a test suite that runs on Windows, Linux and macOS.
