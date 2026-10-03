---
name: contract-init
description: Bootstrap a contract.json for a command-line tool. Use when the user asks to create, initialize, draft, or scaffold a CLI contract, or when their CLI repo does not yet have a contract.
---

# Bootstrap a CLI contract

You help a maintainer write a `contract.json` for their CLI tool from a short
interview, then validate the result.

## How to do it

1. Read `${CLAUDE_PLUGIN_ROOT}/skills/contract-init/references/contract-spec.md`
   so you have the full schema and the rules around `since`, `stability`,
   and `exit_codes` in mind. The spec is small; skim it once per session.
2. Look at the user's repo. If they already have a README, `pyproject.toml`,
   `package.json`, `Cargo.toml`, or source files, use them as ground truth
   for command names, flags, and defaults. Do not invent features they do
   not have.
3. If the user has no source yet, ask the short interview below instead of
   guessing.
4. Build a draft `contract.json`. Always include `schema_version`, `tool`,
   `stability`, `streams`, `exit_codes`, and `commands`. Include
   `environment` and `global_flags` when relevant.
5. Run the validator before showing the result:
   ```
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/validate_contract.py path/to/contract.json
   ```
   Fix every error before you save. Warnings can stay; explain them to the
   user.
6. Show the resulting JSON to the user and ask whether anything should
   change before they commit.

## Short interview (when there is no source to read)

Ask one question at a time. Keep it to six or fewer questions for the first
draft; the user can always refine later.

1. **Tool name and what it does.** "What is the binary called, and what does
   it do in one sentence?"
2. **Subcommands.** "What subcommands does it have, and what does each one
   do?" If none, the tool is a single command and we set `commands` to one
   entry.
3. **Flags per command.** "For each command, what are its flags? What type
   does each take, and what is the default?"
4. **Exit codes.** "What exit codes does it return, and what does each one
   mean? The convention is 0 = success, 1 = general error, 2 = usage error.
   List anything beyond that."
5. **JSON output.** "Does it support a `--json` (or similar) mode for any
   command? If so, since which version, and is there a schema file?"
6. **Audience and stability policy.** "Who uses this in CI, who uses it at
   the terminal? And: what kind of release may break the contract? (minor,
   patch-only, locked, experimental)"

## Tips for the draft

- Use `python3` first when running the validator
  (`${CLAUDE_PLUGIN_ROOT}/scripts/validate_contract.py`); if
  `python3` is not on PATH, fall back to `python` or `py -3`.

- Use `since` for every flag and command, even if the tool is pre-1.0. A
  value like `0.1.0` is fine; the contract keeps its history honest.
  Remember that `since` is immutable: never edit it once a release ships.
- The `name` field on a command can be a single token (`list`), a
  space-separated path (`remote add`), or a colon-separated path
  (`plugins:install`). Tool names are a single token only (`mycli`,
  `MSBuild`).
- Flag names accept underscores (`--dry_run`, `--no_cache_file`) for
  Click compatibility; the validator's `--no-color` style with hyphens
  is the other common form.
- For positional arguments, use the `arguments` field on a command:
  ```
  "arguments": [
    {"name": "SRC", "required": true},
    {"name": "DST", "required": true}
  ]
  ```
- Default `stability` to `stable` for everything that ships to users
  today. Use `experimental` for things the maintainer wants to opt out
  of the contract; the contract-review skill will not count those as
  breaking when they change.
- Use `commands[].notes` for free-form comments. The validator does not
  understand `_comment` fields; only `commands[].notes` is documented
  and preserved through review.

## What to do when the user has an existing partial contract

If they already have a `contract.json` but it is missing fields or has
errors:

1. Run the validator. Capture every error and warning.
2. Show them, grouped: structural errors first, then warnings about
   unknown keys (often typos like `stabilty` or `flgs`), then missing
   recommended fields.
3. Propose a minimal diff that fixes the errors. Do not silently rewrite
   their choices.
4. Re-run the validator until it passes.

## After the draft is accepted

Suggest that the user capture their first set of snapshots using the
structured convention the classifier understands. Both recipes below
run the command once, capture stdout and stderr separately, and write
a snapshot file that starts with `$ cmd`, has `--- stderr` between
the two streams, and ends with `--- exit N`. Create the snapshot
directory first; the recipes do not assume it exists.

POSIX shell (bash, sh, zsh). Tested in bash 5 and dash; `printf
'--- exit %d\n' "$ec"` fails because the format starts with `--`,
so the trailing line uses the end-of-options form:

```sh
mkdir -p snapshots/0.1.0
mytool --help > /tmp/cli-stdout.$$ 2> /tmp/cli-stderr.$$
ec=$?
{
  printf '$ mytool --help\n'
  cat /tmp/cli-stdout.$$
  printf '\n--- stderr\n'
  cat /tmp/cli-stderr.$$
  printf -- '--- exit %d\n' "$ec"
} > snapshots/0.1.0/help.txt
rm -f /tmp/cli-stdout.$$ /tmp/cli-stderr.$$
```

Windows PowerShell 5.1 and PowerShell 7. The redirection `2>
$variable` is not valid in PowerShell (a redirection target is a path
or `*`), and the multi-assignment-with-pipeline form runs and writes
an empty snapshot. The cleanest portable approach is to let `cmd
/c` capture the streams to temp files, then assemble the snapshot
in PowerShell and write it without a UTF-8 BOM (PowerShell's
`Set-Content -Encoding utf8` adds a BOM, which the classifier reads
but which PowerShell 5.1's editor can hide):

```powershell
mkdir snapshots/0.1.0 -ErrorAction SilentlyContinue | Out-Null
$tmpOut = [System.IO.Path]::GetTempFileName()
$tmpErr = [System.IO.Path]::GetTempFileName()
cmd /c "mytool --help > $tmpOut 2> $tmpErr"
$ec = $LASTEXITCODE
$stdout = Get-Content $tmpOut -Raw
$stderr = Get-Content $tmpErr -Raw
$body = @(
    '$ mytool --help'
    $stdout.TrimEnd("`r","`n")
    ''
    '--- stderr'
    $stderr.TrimEnd("`r","`n")
    '--- exit ' + $ec
) -join "`n"
[System.IO.File]::WriteAllText(
    "snapshots/0.1.0/help.txt",
    $body + "`n",
    (New-Object System.Text.UTF8Encoding $false))
Remove-Item $tmpOut, $tmpErr
```

For a `--json` invocation, change the command (`mytool list --json`)
and the snapshot path (`snapshots/0.1.0/list.txt`); the classifier
parses the stdout as JSON.

These snapshots are what the `contract-review` skill will diff against
future versions. Capturing stderr (with `--- stderr`) and the exit
code (with `--- exit N`) at the same time is what lets the classifier
catch exit-code and stream-routing changes that plain `--help` text
would miss.

## Verifying a recipe ran correctly

After running either recipe, the snapshot should look like:

```
$ mytool --help
<command stdout>

--- stderr
<command stderr>

--- exit N
```

Quick check (POSIX):

```sh
test -s snapshots/0.1.0/help.txt && grep -q '^--- exit ' snapshots/0.1.0/help.txt
```

Quick check (PowerShell):

```powershell
Test-Path snapshots/0.1.0/help.txt
Select-String -Path snapshots/0.1.0/help.txt -Pattern '^--- exit '
```

If the second line is missing, the recipe did not capture the exit
code; if `--- stderr` is followed by an empty line and `--- exit`,
the tool did not write to stderr.
