# Classifying snapshot diffs

This file is the playbook for the contract-review skill. Use it when you
classify a change between two snapshot files. The script
`scripts/classify_snapshot_diff.py` produces deterministic evidence; this
file is how you turn that evidence into a verdict.

The verdict is one of:

- **breaking**: a script could fail or misbehave on the new version.
- **compatible**: a script keeps working; humans get a small improvement.
- **cosmetic**: humans might notice; scripts cannot.

When in doubt, classify as **breaking** and explain the doubt. The cost
of over-warning is mild; the cost of under-warning is broken CI for
someone.

## Walk-through

For each hunk the classifier reports:

1. **Read the added and removed lines.** What is changing?
2. **Cross-reference the contract.** If a line names a flag, command, JSON
   key, or exit code that exists in the contract, the contract is your
   source of truth for what the user was promised.
3. **Pick a verdict** using the rules below.
4. **Quote the evidence.** Every verdict names the line(s) that triggered
   it.
5. **Decide the contract update.** A breaking change almost always needs a
   `stability: deprecated` entry plus a CHANGELOG line; a compatible
   change needs an updated `since` on the new entry.
6. **Check policy compliance.** A breaking change is allowed under
   `minor` only when the item was deprecated in the prior minor
   (or earlier). Under `patch-only` a breaking change requires a
   major bump; under `locked` no change is allowed at all (the
   release must wait or the change must be reverted).

## How `stability.policy` constrains the verdict

The contract's `stability.policy` is the maintainer's promise about how
aggressively the contract may change:

| Policy | What is allowed | What a breaking change means |
| --- | --- | --- |
| `minor` | Adding things; deprecating (with one release grace); removing only deprecated items | A new breaking change in a minor release is allowed only if the item being removed was deprecated in the previous minor |
| `patch-only` | Adding things; rephrasing; **no breaking changes** | Any breaking change requires a major bump (or a new policy) |
| `locked` | Nothing | The contract is frozen; any change is out of contract |
| `experimental` | Anything | The contract carries no weight this release |

Always report policy compliance in the verdict block. If the policy is
violated, the review does not just classify the change; it tells the
maintainer to either bump the version (so policy is satisfied) or
restore the previous behaviour.

## How `audiences` affects the verdict

The contract's `audiences` list tells the skill who is being protected:

- `humans` only: terminal users. JSON-shape changes, exit-code
  changes, and stream moves may be downgraded — humans read the
  new shape and try the new exit code themselves. Note them as
  "compatible, note". Help-text and prose changes stay as the
  rules say.
- `scripts` only: CI / pipelines. Help-text changes, prose reflows,
  and default colours may be downgraded — scripts do not parse
  them. Note them as "cosmetic". JSON-shape and stream-routing
  changes stay as the rules say.
- Both: the strict verdict from the rules below applies.

This narrowing never makes a removed surface element invisible.
A removed or renamed flag, command, JSON key, or exit code is
breaking regardless of `audiences`. The narrowing also never makes
something cosmetic that is reported through a stream the audience
captures.

This is the contract's most-asked-for feature: "what counts as
breaking depends on who calls the tool." Apply it.

## How per-item `stability` affects the verdict

A flag or command marked `stability: deprecated` is allowed to be
removed in the *next* release, not the current one. Removal is
breaking unless the deprecated marker was present for at least one
prior release; in that case it is **compatible**. The "Flag removed"
and "Command removed" rows below rely on this rule.

A flag marked `stability: experimental` or `stability: beta` is not
part of the contract yet. Renaming or removing it is **compatible**;
do not count it against the policy.

A flag marked `stability: locked` cannot change at all. Any change to a
locked flag is breaking, period.

## Flag changes

| Change | Verdict | Notes |
| --- | --- | --- |
| New flag added | compatible | Add it to `commands[].flags` with `since` = new version. |
| Flag renamed | breaking | Mark the old name `stability: deprecated` and add the new one. CHANGELOG must say "renamed X to Y". |
| Flag removed | breaking, compatible if `stability: deprecated` was present for at least one prior release | See the per-item stability rule above. |
| Flag type changed (e.g. `string` → `enum`) | breaking | Most parsers will fail. |
| Flag default changed | breaking unless the maintainer confirms no script depends on the old default | Call it out in CHANGELOG either way. A default change is what an unchanged script receives; that is what "breaking" means. |
| Flag short alias changed | breaking | Scripts that pass `-x` will break. |
| Flag `required` flipped | breaking | Existing invocations now fail. |
| Flag accepts new value (loosening) | compatible | Add to `choices` if `enum`. |
| Flag rejects previously accepted value (tightening) | breaking | |
| New `--json` flag on a command | compatible | Add `json_output` block. |
| `enum` choice renamed | breaking | Users scripting on the old name break. |

## Command changes

| Change | Verdict | Notes |
| --- | --- | --- |
| New command added | compatible | Add it to `commands[]` with `since` = new version. |
| Command renamed | breaking | Mark the old name `stability: deprecated` and add the new one. CHANGELOG must say "renamed X to Y". |
| Command removed | breaking, compatible if `stability: deprecated` was present for at least one prior release | See the per-item stability rule above. |
| Positional argument added or removed | breaking | New or removed positionals shift existing invocations. |

## Exit-code changes

| Change | Verdict | Notes |
| --- | --- | --- |
| New exit code added | compatible | Document it in `commands[].exit_codes` and the top-level `$.exit_codes` table. |
| Meaning of an existing code changed | breaking | Document, give users a release to migrate. |
| Code removed from the documented set | breaking | A script that branches on the code now sees something else. |

## JSON-output changes

| Change | Verdict | Notes |
| --- | --- | --- |
| New key added | compatible | Note in CHANGELOG. |
| Key removed | breaking | Restore or deprecate first. |
| Key renamed | breaking | Treat as remove + add. |
| Value type changed (e.g. `"1"` → `1`) | breaking | Strict parsers fail. |
| Array contents reordered | breaking | `jq '.items[0]'` reads positionally. (JSON objects have unordered keys; JSON arrays are ordered.) |
| Wrapping changed (e.g. object → `{items: [...]}`) | breaking | Most consumers will fail. |
| Indentation / whitespace changed | cosmetic | Pretty-printing only. |

## Positional-argument changes

These rows apply to entries in `commands[].arguments[]`, not flags.
Flag `required` has its own row above.

| Change | Verdict | Notes |
| --- | --- | --- |
| New positional added at the end | compatible | Add to `commands[].arguments`. |
| New positional added in the middle | breaking | Existing invocations shift. |
| Required argument flipped from optional to required | breaking | Existing invocations now fail with a usage error. |
| Required argument flipped from required to optional | compatible | Existing invocations still work. |
| Variadic argument added at the end | compatible | Add to `commands[].arguments`. |

## Help-text changes

| Change | Verdict | Notes |
| --- | --- | --- |
| Reworded summary / description | cosmetic | |
| New section added (e.g. `Examples:`) | cosmetic | |
| Section removed | cosmetic | Unless users wrote tools that grepped for it. |
| Default value changed in the prose | breaking unless the maintainer confirms (a help-text default is the runtime default; see the flag table) | Mention in CHANGELOG. |
| A line that used to list a flag no longer does | breaking | The flag is gone or renamed. |

## Stream routing changes

| Change | Verdict | Notes |
| --- | --- | --- |
| Output that used to go to stderr now goes to stdout | breaking | Anyone capturing `2>` breaks. |
| Progress bar moved from stderr to a TTY-only path | compatible | Pipes see clean output. |
| New log line on stderr that wasn't there before | cosmetic | Mention in CHANGELOG. |

## TTY / colour changes

| Change | Verdict | Notes |
| --- | --- | --- |
| Colours appear in TTY mode | cosmetic | Confirm `NO_COLOR` is still respected. |
| Colours leak into piped output | breaking | Breaks `tee`, `less -R`, log aggregators. |
| New `NO_COLOR` support | compatible | |

## What if the change is ambiguous?

- **Different commands in the same snapshot**: classify each command
  separately. A diff that mixes a breaking change in `build` with a
  cosmetic change in `list` is still breaking overall; report both.
- **Newlines-only changes** (line endings, trailing whitespace): cosmetic.
  Mention briefly so the user knows.
- **Reflow of long lines** (wrapping at a different column): cosmetic.
- **A flag's help text changed AND a default changed**: split into two
  entries in the report. One cosmetic, one breaking.

## Combined verdict

When multiple snapshots are reviewed at once (typical: one `--help` and
one `--json` per command), the combined verdict is the worst verdict
from any single snapshot, in this order: **breaking > compatible >
cosmetic**. A single breaking change in one command makes the whole
release breaking, even if everything else is cosmetic.

## Output shape

Always produce a Verdict line, a Policy line, and four sections. The
shape is fixed so the maintainer can grep it, paste it into a PR, and
have Claude generate the matching CHANGELOG entry without ambiguity.

```
## Verdict: <breaking | compatible | cosmetic>
## Policy: <allowed | violation: needs major bump | locked>

### Per-change summary
- <change>: <verdict> -- <one-line reason>

### Evidence
1. <quote of lines from the diff with line numbers>
2. ...

### Suggested contract.json update
<JSON patch or full command block>

### CHANGELOG entry
- <bullet>
- <bullet>
```
