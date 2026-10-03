# Producing contract.json updates from a review

Once the contract-review skill has classified the diff, it needs to
express the verdict as a change to `contract.json`. This file is the
playbook for *how* to write the patch.

## Read first

- `${CLAUDE_PLUGIN_ROOT}/skills/contract-init/references/contract-spec.md`
  for the schema (which fields exist, which are required, what each
  one means). Substitute the plugin's installed directory when
  reading.
- `${CLAUDE_PLUGIN_ROOT}/skills/contract-review/references/classification-rules.md`
  for the verdict of a given change (breaking, compatible, cosmetic).
  This document never restates the verdict; it points at the rules.

A change that is breaking under the rules stays breaking here too. If
the playbook below and the rules ever disagree, the rules win; please
fix the playbook.

## Patterns

### "Add a new flag" (compatible)

```json
{
  "name": "--filter",
  "type": "string",
  "default": null,
  "since": "1.2.0",
  "stability": "stable"
}
```

Place it in `commands[cmd].flags` (or `global_flags`). Use the new
release version as `since`.

### "Deprecate a flag"

Two steps:

1. Add `"stability": "deprecated"` to the existing flag entry. Keep
   everything else. The validator accepts this combination.
2. Note in CHANGELOG: "Deprecated `--x`. It will be removed in 2.0.0."

The flag still appears in `flags`, just with `stability: deprecated`.

### "Rename a flag"

Two steps, ordered carefully:

1. Add the new flag with `since` = new version, `stability: stable`.
2. Edit the old flag entry to `"stability": "deprecated"`.

Both stay in the contract for one release. Do not delete the old entry
on the same release as the rename; downstream parsers will explode.
The verdict for a rename comes from the rules table.

### "Remove a flag"

After the deprecated release ships, remove the flag entry from
`flags`. Under the per-item stability rule the removal itself is
**compatible** (the deprecation served as the one-release grace).
The release that drops the entry is not required to be a major
bump; what matters is that the flag carried
`stability: deprecated` for at least one prior release.

### "Add a JSON output mode" (compatible)

For a command that did not have one:

```json
"json_output": {
  "stable_since": "1.2.0",
  "schema": "schemas/<command>.schema.json"
}
```

For a command that already had one: do not edit `stable_since`; add a
CHANGELOG line for the new keys.

### "Add a JSON key" (compatible)

Just a CHANGELOG line. Do not bump `json_output.stable_since`; the
shape is allowed to grow.

### "Remove a JSON key"

The rules classify a key removal as breaking. Bump
`json_output.stable_since` to the new version only if the maintainer
is treating the new shape as the frozen one and keeping the old key
for one release under a deprecated alias. Otherwise this is a
breaking change and the maintainer should call it out in the
CHANGELOG with a major bump.

### "Add an exit code" (compatible)

Add an entry to the top-level `exit_codes` table and reference it from
the relevant `commands[].exit_codes`. The validator warns if the code
is referenced before it is defined; silence that warning by adding
the table entry first.

### "Change a flag default"

The rules classify a default change as breaking unless the maintainer
confirms no script depends on the old default. Update the flag's
`default` field and the CHANGELOG either way; the version bump is
the maintainer's call.

### "Move output between streams"

`streams` documents the maintainer's promise. When a stream move is
intentional, edit `streams.stdout` / `streams.stderr` and call it out
in the CHANGELOG. The change is breaking for any script that captures
stderr.

### "Add a new command" (compatible)

Add a `commands` entry. Use the new release version as `since`.

### "Remove a command"

Requires a previous `stability: deprecated` entry. Remove the entry
from `commands` and the CHANGELOG.

## How to present the patch

Give the user a JSON Patch (RFC 6902) when the change is small. For
larger changes, show the full updated command block.

When the user is ready to apply the patch, run the validator on the
updated file. Tell the user the command to run, expanding
`${CLAUDE_PLUGIN_ROOT}` to the plugin's installed directory:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/validate_contract.py contract.json
```

## Note: contract changes follow code changes

The review workflow assumes the source code has already shipped. A
contract that documents something the tool no longer does is
misleading. When you discover a breaking change during review, the
fix is in the code first:

- Renamed flag → restore the old name as a hidden alias that prints a
  deprecation warning to stderr. Then update the contract with the
  new entry and `stability: deprecated` on the old one.
- Removed flag → restore it for one release (or document it under
  `stability: deprecated` if the source cannot change).
- Changed exit-code meaning → restore the previous meaning for any code
  that the contract still lists.

After the code change, update the contract. The point is that the
contract documents what users can rely on; the binary must continue
to provide it for at least one release.

## Versioning hints

- `since` records the version a feature was introduced. It is
  historical: do not edit it once a release ships, even when the
  feature changes in a later release. New entries get a new `since`,
  not an update to the old one.
- `stability` is the only field the maintainer can downgrade cheaply.
  Use that to signal the deprecation path (`stable` → `deprecated` →
  removal).
- The schema's own `schema_version` only bumps for breaking changes in
  the contract format itself, not for changes in the CLI being
  described.
