# Worked example: 1.0.0 to 1.1.0 review

This file is what a contract-review session produces for the demo CLI.
It is included so a reader can see exactly what the plugin's output
looks like without running it themselves.

To reproduce:

```
python scripts/validate_contract.py examples/demo-cli/contract.1.0.0.json
python scripts/classify_snapshot_diff.py \
    examples/demo-cli/snapshots/1.0.0/list-help.txt \
    examples/demo-cli/snapshots/1.1.0/list-help.txt
python scripts/classify_snapshot_diff.py \
    examples/demo-cli/snapshots/1.0.0/list-json.txt \
    examples/demo-cli/snapshots/1.1.0/list-json.txt
```

The two `classify_snapshot_diff.py` invocations below are real,
unedited runs of the classifier on the shipped snapshots. The line
numbers match the source files (stdout starts at file line 4 in the
1.0.0 help file: line 1 is `$ cmd`, lines 2 and 3 are `Usage:` and
blank).

## Inputs

- Before snapshot: `snapshots/1.0.0/list-help.txt`
- After snapshot: `snapshots/1.1.0/list-help.txt`
- Before snapshot: `snapshots/1.0.0/list-json.txt`
- After snapshot: `snapshots/1.1.0/list-json.txt`
- Contract under review: `contract.1.0.0.json` (the published state)
- Contract after the review is applied: `contract.json` (the 1.1.0 state)
- `stability.policy`: `minor`
- `stability.audiences`: `humans`, `scripts`

## Verdict: breaking

## Policy: violation: needs major bump

The contract's policy is `minor`. One of the changes below removes a
`stable` global flag with no prior `stability: deprecated` release. Under
a `minor` policy, that is not allowed; the release must be a major
bump or the flag must be restored as a deprecated alias for one
release first.

## Per-change summary

- `list.help` `--no-color` removed: breaking. Stable global flag gone
  with no deprecation grace.
- `list.help` `--filter` added: compatible. New flag, set `since` to
  the new version.
- `list.help` `--limit` default changed 20 to 50: breaking unless the
  maintainer confirms no script depends on the old default. The CI
  script in the same release that does `tasks list | head -20` now
  gets 50 rows.
- `list.help` `--format` gained `ndjson` as a choice: compatible. The
  `enum` widened; old choices still accepted.
- `list.help` exit code 2 added to the prose and to `$.exit_codes`:
  compatible. Code 2 was not previously documented in
  `$.exit_codes`; the patch adds the table entry. (The matching
  prose line was added in the same release.)
- `list.help` `Examples:` section added: cosmetic. Help-text only.
- `list.json` every item gained a `tags` array: compatible. Additive
  JSON change inside the documented `items[].*` shape.

## Evidence

Real output of `classify_snapshot_diff.py snapshots/1.0.0/list-help.txt
snapshots/1.1.0/list-help.txt`:

```
--- diff (10 added, 6 removed)
    4 List tasks from the local store.
    5
    6 Options:
-   7   -n, --limit <N>    Maximum number of tasks to show (default: 20)  [flag]
+   7   -n, --limit <N>        Maximum number of tasks to show (default: 50)  [flag]
-   8   --format <FMT>     Output format: text or json (default: text)  [flag]
+   8   --format <FMT>         Output format: text, json, or ndjson (default: text)  [flag]
-   9   --json             Emit machine-readable JSON  [flag]
+   9   --json                 Emit machine-readable JSON  [flag]
-  10   --no-color         Disable colored output  [flag]
+  10   --filter <PATTERN>     Only show tasks matching PATTERN  [flag]
-  11   -h, --help         Show this help and exit  [flag]
+  11   -h, --help             Show this help and exit  [flag]
   12
-  13 Exit code: 0 on success, 1 on error.  [exit-code:0]  [exit-code:1]
+  13 Exit code: 0 on success, 1 on error, 2 on usage error.  [exit-code:0]  [exit-code:1]  [exit-code:2]
   14
+  15 Examples:
+  16   tasks list --limit 5  [flag]
+  17   tasks list --format ndjson | jq -c '.id'  [flag]
+  18

--- signals (these are evidence, not a verdict)
  before command: tasks list --help
  after command:  tasks list --help
  flags added:    ['--filter']
  flags removed:  ['--no-color']
  flags present on both sides (read the diff; a default, type or choices change still hides here): ['--format', '--help', '--json', '--limit', '-h', '-n']
  exit codes added:   ['exit-code:2']
```

Real output of `classify_snapshot_diff.py snapshots/1.0.0/list-json.txt
snapshots/1.1.0/list-json.txt --json` (truncated to the summary and
the first two records for brevity; the full output has nine records):

```
{
  "identical": false,
  "summary": {
    "added_lines": 2,
    "removed_lines": 2,
    "context_lines": 5,
    "flags_added": [],
    "flags_removed": [],
    "flags_present_on_both_sides": [],
    "exit_codes_added": [],
    "exit_codes_removed": [],
    "json_changes": [
      {"path": "/items[0].tags", "change": "added", "after": ["docs"]},
      {"path": "/items[1].tags", "change": "added", "after": ["release"]}
    ],
    "before_command": null,
    "after_command": null
  },
  "records": [
    {"op": "context", "before_no": 1, "after_no": 1, "line": "{", "labels": ["json-brace"]},
    {"op": "context", "before_no": 2, "after_no": 2, "line": "  \"items\": [", "labels": ["json-key"]}
  ]
}
```

The structural diff reports the additive key on each item; the text
diff (omitted) confirms the change is purely additive.

## Suggested contract.json update

The patch below turns the 1.0.0 contract into the 1.1.0 contract.

```diff
   "exit_codes": [
     {"code": 0, "meaning": "success"},
-    {"code": 1, "meaning": "runtime error"}
+    {"code": 1, "meaning": "runtime error"},
+    {"code": 2, "meaning": "usage error"}
   ],
   "global_flags": [
-    {"name": "--json", "type": "bool", "since": "0.1.0", "stability": "stable"},
-    {"name": "--no-color", "type": "bool", "since": "0.1.0", "stability": "stable"}
+    {"name": "--json", "type": "bool", "since": "0.1.0", "stability": "stable"}
   ],
   "commands": [
     {
       "name": "list",
-      "exit_codes": [0, 1],
+      "exit_codes": [0, 1, 2],
       "flags": [
         {
           "name": "--format",
           "type": "enum",
-          "choices": ["text", "json"],
+          "choices": ["text", "json", "ndjson"],
           "default": "text",
           "since": "0.1.0",
           "stability": "stable"
         },
         {
           "name": "--limit",
-          "default": 20,
+          "default": 50,
           "since": "0.1.0",
           "stability": "stable"
-        }
+        },
+        {
+          "name": "--filter",
+          "type": "string",
+          "since": "1.1.0",
+          "stability": "stable"
+        }
       ],
```

`--no-color` is removed entirely from the new contract. Under the
recommended code-first deprecation path it would stay as
`stability: deprecated` for one release instead.

## CHANGELOG entry

```
## 2.0.0

### Breaking
- The `--no-color` global flag is removed. The 1.0.0 contract never
  marked it as deprecated, so under a `minor` stability policy this
  requires a major bump. Either ship the flag as `stability:
  deprecated` for one release and remove in 2.0.0, or restore the
  flag at this release and remove it in 2.0.0 (see "What the
  maintainer should do").
- `tasks list --limit` now defaults to 50; the previous default was
  20. Treat this as breaking unless you confirm no script depends
  on the old default; CI scripts that pipeline through `head` will
  now get more rows. The CHANGELOG entry for the 2.0.0 release
  should repeat this bullet or, if the maintainer confirms the
  default change is safe, drop it from this heading.

### Compatible
- `tasks list --filter PATTERN` limits the output to items matching
  PATTERN.
- `tasks list --format` accepts `ndjson` in addition to `text` and
  `json`.
- `tasks list --json` items now include a `tags` array.
- Exit code 2 (usage error) is now documented in `$.exit_codes` and
  referenced from `tasks list`.

### Cosmetic
- `tasks list --help` gained an `Examples:` section.
```

## What the maintainer should do

The review says `breaking` because `--no-color` was a stable flag in
the 1.0.0 contract and the new release has not yet shipped a
deprecated version. The reference doc on contract updates says:
when a breaking removal is caught during review, the fix is in the
code first. Two viable paths:

1. **Accept the break.** Bump the release to `2.0.0`, document
   the removal in the CHANGELOG, and let users migrate. The
   `--no-color` flag is gone from the binary. This is the path
   the CHANGELOG above assumes.
2. **Restore as deprecated for one release.** Keep the release at
   `1.1.0`. Reintroduce `--no-color` in the binary as a hidden
   alias that prints to stderr and exits 0, and update the
   contract with `stability: deprecated` for the flag. The next
   release (2.0.0) then removes the alias. This makes the next
   contract review read "compatible" for the same diff.

The reviewer in round 4 noted that round 3's "path 1 keeps the
binary behaviour you shipped" was wrong: path 1 *removes* the flag
from the binary. The two paths do not contradict; they are two
distinct release plans.
