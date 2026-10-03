# Stable-output checklist

This file is the long-form version of the `contract-design` skill. When the
maintainer asks a general question about CLI stability, draw on the
sections here. Use the bullets as a checklist you can paste into their
README or design doc.

## Stream routing

Rule of thumb: **data on stdout, diagnostics on stderr.**

- **stdout** carries the result the user asked for. Captured by default.
- **stderr** carries anything that helps a human debug but does not change
  the result: progress bars, verbose logs, deprecation warnings.

Concretely, do not:

- Print a startup banner on stdout. Print it on stderr, gate it behind a
  `--version` flag, or drop it. A banner on stdout is invisible to CI
  scripts that capture `2>` for diagnostics and visible to every script
  that pipes the output, neither of which is what you want.
- Mix log lines with structured output on stdout. A script that pipes to
  `jq` should not have to filter out `INFO: connected` first.

By contrast:

- `--help` writes to stdout by convention and should stay there. CI
  scripts that grep the help text depend on it; moving help to stderr
  silently breaks them.
- `--version` writes to stdout. The convention is `tool --version` →
  `tool 1.2.3\n` on stdout. That is what package managers and tooling
  expect.

## Exit codes

Keep them few and stable. The conventional split:

| Code | Meaning |
| --- | --- |
| 0 | success |
| 1 | runtime / general error |
| 2 | usage error (bad flag, missing arg) |
| 64+ | follow BSD sysexits.h (`EX_USAGE`=64, `EX_DATAERR`=65, etc.) if you want a richer vocabulary |

Document every code you ship. The contract's `exit_codes` table is where
that documentation lives. Avoid changing the meaning of a code in a minor
release; it will break every script that branches on it.

## JSON output

The hardest part. JSON looks easy because it parses, but the parser is
the smallest part of the contract.

- **Pick a stable schema.** Use JSON Schema and ship it in the repo. The
  contract's `json_output.schema` is the pointer.
- **Treat the schema as append-only within a major.** Adding keys is
  compatible; renaming or removing is breaking. The verdict for any
  specific change lives in
  `skills/contract-review/references/classification-rules.md` (the
  single source of truth for breaking/compatible/cosmetic); this
  document only states the design principle.
- **Do not change value types.** `"1"` to `1`, `null` to `[]`, `{}` to
  `{items: []}` are all breaking for strict consumers.
- **Treat arrays as ordered.** JSON objects have unordered keys; JSON
  arrays have positional order, and `jq '.items[0]'` reads the first
  element. Reordering a JSON array is breaking (the classification
  rules have the rule).
- **Wrap or top-level?** Pick one and stay with it. A common pattern is
  a top-level object with a `data` key and a `meta` key, so you have
  somewhere to add pagination later without breaking the array shape.

## TTY awareness

Detect the TTY, not the parent process. Use the same call your language's
standard library uses (Node: `process.stdout.isTTY`, Python: `sys.stdout.isatty()`).

- In a TTY: colour, progress bars, prompts.
- Not in a TTY: plain text, no animation, no prompts. Most importantly,
  no ANSI escape codes on stdout — they look like noise to log
  aggregators.

Respect **`NO_COLOR`**. The convention is: if the variable is set to any
non-empty value, disable colour. Do not require a specific value; "no" and
"false" both mean "no colour".

Respect **`TERM=dumb`**. The terminal said it is dumb; believe it.

## `--json` mode

When a command supports JSON, it should be **the same data as the
human-readable output**, just structured. It should not be a side channel
that lags behind the human output by a release.

- Keep the JSON shape independent of locale. Numbers stay numbers.
- Timestamp format: RFC 3339 with a timezone, or epoch milliseconds.
  Pick one; document it in the schema.
- Validate the output against the shipped schema in CI. A shape that
  drifts without anyone noticing is the worst kind of breaking change.

## Environment variables

Document every variable the tool reads. The contract's
`environment.respects` is the place.

Common ones:

- `NO_COLOR` — disable ANSI escapes
- `TERM` — terminal capability hint
- `LANG` / `LC_ALL` — locale for messages
- `XDG_CONFIG_HOME` — config file location
- `EDITOR` — fallback for `$EDITOR`-style prompts
- `CI` — many tools change behaviour in CI (no progress, no prompts)

Do not invent new variables for things flags can express.

## Help text

- Write `--help` as if a stranger will read it. Strangers do, in CI logs.
- One-line summary at the top.
- Examples near the bottom, runnable as pasted.
- Group flags by category: input, output, networking, debugging.
- Avoid ASCII art that depends on a fixed terminal width.
- Flag order is not a contract. Reordering or reflowing the help
  output is cosmetic by the verdict rules; humans who read help by
  skimming notice, scripts that grep a single flag do not.

## Prompting

Avoid prompts when **stdin** is not a TTY. There is no human to answer;
the process will hang. A non-interactive stdout (a pipe, a redirect) is
not enough — the prompt still reads from stdin.

When you must prompt:

- Document every prompt in the contract (a `prompts` block is a fine
  extension; add it when you need it).
- Allow a `--yes` / `--no` flag for each prompt.
- Honour `CI` to skip prompts.

## Versioning

The contract's `stability.policy` says what kind of release may break the
contract. Be honest about it:

- `patch-only` is the safest promise. You can add flags, never remove.
- `minor` is the typical promise. You can deprecate, then remove one
  minor later.
- `locked` is for tools that have stopped changing.
- `experimental` is the honest answer for tools still finding their
  shape.

## What to do next

Once the maintainer is comfortable with the design, hand off to the
`contract-init` skill to capture the choices in `contract.json`. Once a
contract exists, the `contract-review` skill will keep them honest at
every release.
