# Changelog

## 1.1.0

The shape of `tasks list --json` grew a `tags` array on each item. The
`--no-color` global flag was removed; `--filter` was added; the default
for `--limit` changed from 20 to 50; an `Examples:` section was added to
`--help`. The contract's `commands.list.exit_codes` now also references
code 2 (usage error).

## 1.0.0

Initial release of the demo CLI: `tasks list` and `tasks add`.
