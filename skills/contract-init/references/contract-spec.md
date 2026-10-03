# Contract schema (version 1)

A `contract.json` describes the **public surface** of a CLI tool: the commands,
flags, exit codes, and outputs the maintainer promises to its users. This file
is the source of truth. `scripts/validate_contract.py` enforces it; the
contract-review skill reads it; the contract-init skill produces it.

The schema is intentionally small. Anything you cannot express here, mark
`stability: experimental` and document in the command's `notes`. The contract
should be pleasant to maintain for years, so it favours plain JSON keys over
nesting. Keys starting with `x-` are reserved for extensions and pass
validation silently.

## Top-level shape

```
{
  "schema_version": "1",
  "tool":            { ... },
  "stability":       { ... },
  "streams":         { ... },
  "exit_codes":      [ ... ],
  "environment":     { ... },
  "global_flags":    [ ... ],
  "commands":        [ ... ]
}
```

`schema_version`, `tool`, `stability`, and `commands` are required. Every
other field is recommended; the validator emits an error when one is
present but malformed (wrong type, out-of-range value, unknown enum, etc.)
and a warning for unknown keys at any level so a typo does not silently
disable a promise.

## `schema_version`

Required. Currently the only accepted value is `"1"`. Bump it whenever the
schema shape changes in a non-backwards-compatible way; the validator
explicitly rejects unknown versions so maintainers notice before they merge.

## `tool`

Required object.

| Field | Type | Notes |
| --- | --- | --- |
| `name` | string, required | Single token; letters, digits, `.`, `_`, `-`. Tool names do not contain spaces (a binary is one word); mixed case is allowed (`MSBuild`, `getUser`). |
| `display_name` | string | Human-friendly title shown in error messages. |
| `description` | string | One-paragraph summary. |
| `homepage` | string | URL. |

## `stability`

Required object. Describes how aggressively the contract may change and
who the contract protects.

| Field | Allowed values | Meaning |
| --- | --- | --- |
| `policy` | `minor` / `patch-only` / `locked` / `experimental` | What kind of release may break the contract. `minor` lets the contract shift on minor releases; `patch-only` forbids any breaking change inside a minor; `locked` freezes the contract at the current version; `experimental` removes all stability promises. The contract-review skill reports whether the verdict for the diff is allowed under this policy. |
| `audiences` | subset of `humans`, `scripts` | Who the contract protects. `humans` = terminal users, `scripts` = CI / pipelines. At least one. The contract-review skill weights changes by audience: JSON-shape changes are not breaking for `humans`-only; help-text changes are not breaking for `scripts`-only. |

## `streams`

Optional object. Documents the maintainer's promise about stream routing.

| Field | Type | Notes |
| --- | --- | --- |
| `stdout` | string | What the maintainer promises goes to stdout, e.g. "data and primary output only". |
| `stderr` | string | What the maintainer promises goes to stderr, e.g. "diagnostics, progress, errors only". |

The maintainer should not rely on this contract catching every stream misuse;
the validator only checks the field exists and is a string. The contract-review
skill uses this as evidence when classifying a snapshot diff.

## `exit_codes`

Optional but strongly recommended. A list of objects:

```
{ "code": 0, "meaning": "success" }
```

- `code`: integer 0..255, unique within the list.
- `meaning`: non-empty string the maintainer writes for users.

If a command lists `exit_codes`, the validator warns when a code referenced
there is not present in this table. Reference any code you actually use, but
do not invent new codes per release.

## `environment`

Optional object documenting how the tool reacts to its environment.

| Field | Type | Notes |
| --- | --- | --- |
| `respects` | list of strings | Environment variables honoured, e.g. `["NO_COLOR", "TERM"]`. |
| `tty_aware` | boolean | When `true`, the tool produces different output in a TTY (colours, progress) versus a pipe (plain text). |
| `json_flag` | string | The name of the global flag that switches output to JSON, e.g. `"--json"`. |

## `global_flags`

Optional list of flags that apply to every command. Same shape as
`commands[].flags`.

## `commands`

Required list. Each entry:

| Field | Type | Notes |
| --- | --- | --- |
| `name` | string | A single token (`list`), a space-separated path (`remote add`), or a colon-separated path (`plugins:install`). Unique within the contract. Mixed case is allowed (`getUser`). |
| `summary` | string | One-line description of what the command does. |
| `since` | semver string (`x.y.z`) | First release the command was present. Immutable: do not edit once a release ships. |
| `stability` | one of `experimental`, `beta`, `stable`, `locked`, `deprecated` | Default to `stable` once you ship to users. |
| `exit_codes` | list of integer | Documented subset of `$.exit_codes`, range 0..255. |
| `arguments` | list of argument objects | See below. Positional arguments, in declaration order. |
| `flags` | list of flag objects | See below. |
| `stdout_format` | one of `human`, `text`, `json`, `tsv`, `csv`, `ndjson`, `none` | What `stdout` carries by default. |
| `stderr_format` | same | What `stderr` carries. |
| `json_output` | object or `null` | See below. |
| `notes` | string | Free-form context for maintainers. |

### `commands[].arguments[]`

Optional list, declaration order. Positional arguments are a classic
breaking-change site; track them here so a future review can spot a
count change, a required flip, or a new middle argument.

| Field | Type | Notes |
| --- | --- | --- |
| `name` | string, required | Uppercase by convention (`PATH`, `SRC`, `DST`). |
| `required` | boolean | Defaults to `true`; set `false` for optional positionals. |
| `variadic` | boolean | Absorbs remaining arguments. Only the last argument may be variadic. |
| `since` | semver string | First release the argument existed. Immutable. |
| `description` | string | One-line help text. |

### `commands[].flags[]`

| Field | Type | Notes |
| --- | --- | --- |
| `name` | `--word`, `--snake_case`, or `-x` | Required. Unique within the command. Underscores are accepted because Click and many hand-written CLIs use them. |
| `short` | `-x` | Optional one-letter alias. |
| `type` | one of `string`, `int`, `float`, `bool`, `path`, `enum`, `list`, `count` | Required. |
| `default` | depends on `type` | Optional. The validator checks the type matches. |
| `required` | boolean | Optional. |
| `choices` | list of strings | Required when `type` is `enum`. Each entry must be a string. |
| `description` | string | One-line help text. |
| `since` | semver string | First release the flag was present. Immutable: do not edit once a release ships. |
| `stability` | same enum as command-level | Lets you ship a flag as `beta` before promoting. |

### `commands[].json_output`

When present (object), marks that the command supports machine-readable JSON
output.

```
"json_output": {
  "stable_since": "1.2.0",
  "schema": "schemas/list.schema.json"
}
```

| Field | Type | Notes |
| --- | --- | --- |
| `stable_since` | semver string | First release the JSON shape was frozen. Adding keys after that is fine; removing or renaming is breaking. |
| `schema` | string path | Relative path to a JSON Schema the maintainer ships. |
| `notes` | string | Optional. |

A `null` value means: the command does not have a JSON mode.

## What "breaking" means here

The full table lives in
`${CLAUDE_PLUGIN_ROOT}/skills/contract-review/references/classification-rules.md`;
that document is the single source of truth and is what the
contract-review skill applies. This section is a one-paragraph
summary for readers who are writing a contract for the first time and
do not want to open another file:

- Anything a script could depend on changing is breaking: a removed
  or renamed flag, command, JSON key, or exit code; a default that
  an unchanged script used to receive; tightened input validation; a
  moved stream.
- Widening is compatible: a new flag, command, JSON key, exit code;
  an `enum` choice added; an input that used to be rejected now
  accepted.
- Help-text rephrasing and column reflow are cosmetic, but record
  them so users can scan the diff.
- The classification rules weigh each verdict by `stability.policy`,
  `stability.audiences`, and the per-item `stability` field; see
  that document for the exact table.

When in doubt, classify as breaking. The cost of over-warning is
mild; the cost of under-warning is broken CI for someone.

## How to evolve the contract

When you ship a new release:

1. Add new flags, JSON keys, exit codes. Each new entry gets its own
   `since` set to the new release version.
2. Mark removed items `stability: "deprecated"` and ship them for one
   release before removing. A "deprecated" entry still documents what
   users relied on.
3. Bump the tool's own version, not the `schema_version`. The schema
   version only changes when the contract format itself changes in a
   non-backwards-compatible way.
4. Do **not** edit `since` on existing entries. The field records the
   first release the feature was present; it is a piece of history.
