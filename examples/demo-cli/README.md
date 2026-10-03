# Demo CLI (worked example)

A tiny synthetic CLI that ships with CLI Contract Guard so you can see
what a real review looks like without setting up your own tool. The
files here are fixtures, not a working binary.

## Layout

```
contract.json                    # The CLI contract in the 1.1.0 state
contract.1.0.0.json              # The CLI contract as it was at 1.0.0
snapshots/
  1.0.0/
    list-help.txt                # Captured `tasks list --help` for v1.0.0
    list-json.txt                # Captured `tasks list --json` for v1.0.0
  1.1.0/
    list-help.txt                # Captured `tasks list --help` for v1.1.0
    list-json.txt                # Captured `tasks list --json` for v1.1.0
EXAMPLE-VERDICT.md               # A worked review of the v1.0.0 -> v1.1.0 diff
CHANGELOG.md                     # A plausible changelog for both versions
schemas/
  list.schema.json               # JSON Schema referenced by `json_output.schema`
```

## Try the plugin on it

Validate the published (1.1.0) contract:

```
python3 scripts/validate_contract.py examples/demo-cli/contract.json
```

Validate the pre-update (1.0.0) contract:

```
python3 scripts/validate_contract.py examples/demo-cli/contract.1.0.0.json
```

Diff the help snapshots:

```
python3 scripts/classify_snapshot_diff.py \
    examples/demo-cli/snapshots/1.0.0/list-help.txt \
    examples/demo-cli/snapshots/1.1.0/list-help.txt
```

Diff the JSON snapshots:

```
python3 scripts/classify_snapshot_diff.py \
    examples/demo-cli/snapshots/1.0.0/list-json.txt \
    examples/demo-cli/snapshots/1.1.0/list-json.txt
```

Then read `EXAMPLE-VERDICT.md` for the review the contract-review skill
would produce. The verdict says the release is breaking under the
contract's `policy: minor` because the `--no-color` global flag was
removed without a prior `stability: deprecated` release. The full
verdict rules live in
`skills/contract-review/references/classification-rules.md`; the
EXAMPLE-VERDICT applies them.
