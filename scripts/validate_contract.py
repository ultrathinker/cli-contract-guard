#!/usr/bin/env python3
"""Validate a CLI contract.json against the CLI Contract Guard schema.

This is a hand-rolled validator: no third-party dependencies, no JSON Schema
package. The rules live here so the source is the spec.

Exit codes:
  0  contract is valid (warnings may still be present)
  1  contract is invalid (one or more errors)
  2  usage error (missing file, malformed JSON)

Usage:
  python3 validate_contract.py path/to/contract.json
  python3 validate_contract.py path/to/contract.json --json   # machine-readable output
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

SCHEMA_VERSION = "1"

STABILITY_VALUES = {"experimental", "beta", "stable", "locked", "deprecated"}
POLICY_VALUES = {"minor", "patch-only", "locked", "experimental"}
AUDIENCE_VALUES = {"humans", "scripts"}
FLAG_TYPES = {"string", "int", "float", "bool", "path", "enum", "list", "count"}
STDOUT_FORMATS = {"human", "text", "json", "tsv", "csv", "ndjson", "none"}
SEMVER = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$")
# A command name may be a single token (the common case) or a path of
# tokens separated by spaces or colons: `remote add`, `plugins:install`,
# `topic subcommand`. Hyphens, underscores, and digits are allowed inside
# each segment. Uppercase letters are accepted because real CLIs name
# things like `getUser`, `MSBuild`, and `PubKeys`.
COMMAND_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*(\s[A-Za-z0-9][A-Za-z0-9._:-]*)*$")
# Tool names are short single tokens (the binary name) without spaces;
# the broader character set above would be confusing here.
TOOL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
# Underscores are common in real CLI flag names (`--dry_run`,
# `--no_cache_file`); this regex matches them.
FLAG_NAME = re.compile(r"^-{1,2}[A-Za-z][A-Za-z0-9_-]*$")
FLAG_SHORT = re.compile(r"^-[A-Za-z0-9]$")
EXTENSION_PREFIX = "x-"

# Valid keys at each level of the contract. Unknown keys are reported as
# warnings so a typo does not silently disable a promise the maintainer
# thought they had. Keys starting with "x-" are reserved for extensions
# and pass through silently.
KNOWN_KEYS: dict[str, set[str]] = {
    "$": {
        "schema_version",
        "tool",
        "stability",
        "streams",
        "exit_codes",
        "environment",
        "global_flags",
        "commands",
    },
    "tool": {"name", "display_name", "description", "homepage"},
    "stability": {"policy", "audiences"},
    "streams": {"stdout", "stderr"},
    "environment": {"respects", "tty_aware", "json_flag"},
    "exit_code_entry": {"code", "meaning"},
    "flag": {
        "name",
        "short",
        "type",
        "default",
        "required",
        "choices",
        "description",
        "since",
        "stability",
    },
    "command": {
        "name",
        "summary",
        "since",
        "stability",
        "exit_codes",
        "flags",
        "stdout_format",
        "stderr_format",
        "json_output",
        "notes",
        "arguments",
    },
    "json_output": {"stable_since", "schema", "notes"},
    "argument": {"name", "required", "variadic", "since", "description"},
}


class Issue:
    __slots__ = ("severity", "path", "message")

    def __init__(self, severity: str, path: str, message: str) -> None:
        self.severity = severity
        self.path = path
        self.message = message

    def to_dict(self) -> dict[str, str]:
        return {"severity": self.severity, "path": self.path, "message": self.message}


def is_semver(value: Any) -> bool:
    return isinstance(value, str) and bool(SEMVER.match(value))


def is_flag_name(value: Any) -> bool:
    return isinstance(value, str) and bool(FLAG_NAME.match(value))


def is_flag_short(value: Any) -> bool:
    return isinstance(value, str) and bool(FLAG_SHORT.match(value))


def is_ident(value: Any) -> bool:
    return isinstance(value, str) and bool(COMMAND_NAME.match(value))


def is_tool_name(value: Any) -> bool:
    return isinstance(value, str) and bool(TOOL_NAME.match(value))


def check_unknown_keys(obj: dict[str, Any], level: str, path: str, issues: list[Issue]) -> None:
    """Warn about keys that are not part of the schema.

    Keys prefixed with `x-` are reserved for extensions and pass through
    silently. The unknown-key warning is what catches `stabilty` and
    `flgs`: a typo silently disables a promise the maintainer thought they
    had, which is the worst failure mode for a file that is supposed to
    hold for years.
    """
    known = KNOWN_KEYS.get(level, set())
    for key in obj:
        if key.startswith(EXTENSION_PREFIX):
            continue
        if key not in known:
            issues.append(
                Issue(
                    "warning",
                    f"{path}.{key}",
                    f"unknown key {key!r} at this level (allowed: {sorted(known)})",
                )
            )


def validate(data: Any, issues: list[Issue]) -> None:
    """Walk the contract and append issues. Mutates `issues` in place."""

    if not isinstance(data, dict):
        issues.append(Issue("error", "$", "contract must be a JSON object"))
        return

    check_unknown_keys(data, "$", "$", issues)

    sv = data.get("schema_version")
    if sv is None:
        issues.append(Issue("error", "$.schema_version", "schema_version is required"))
    elif sv != SCHEMA_VERSION:
        issues.append(
            Issue(
                "error",
                "$.schema_version",
                f"unsupported schema_version {sv!r}; this validator handles {SCHEMA_VERSION!r}",
            )
        )

    tool = data.get("tool")
    if not isinstance(tool, dict):
        issues.append(Issue("error", "$.tool", "tool must be an object"))
    else:
        check_unknown_keys(tool, "tool", "$.tool", issues)
        name = tool.get("name")
        if not isinstance(name, str) or not name:
            issues.append(Issue("error", "$.tool.name", "tool.name must be a non-empty string"))
        elif not is_tool_name(name):
            issues.append(
                Issue(
                    "error",
                    "$.tool.name",
                    f"tool.name {name!r} must match {TOOL_NAME.pattern}",
                )
            )
        display = tool.get("display_name")
        if display is not None and not isinstance(display, str):
            issues.append(Issue("error", "$.tool.display_name", "tool.display_name must be a string"))
        if tool.get("homepage") is not None and not isinstance(tool["homepage"], str):
            issues.append(Issue("error", "$.tool.homepage", "tool.homepage must be a string"))
        if tool.get("description") is not None and not isinstance(tool["description"], str):
            issues.append(Issue("error", "$.tool.description", "tool.description must be a string"))

    stability = data.get("stability")
    if not isinstance(stability, dict):
        issues.append(Issue("error", "$.stability", "stability must be an object"))
    else:
        check_unknown_keys(stability, "stability", "$.stability", issues)
        policy = stability.get("policy")
        if policy not in POLICY_VALUES:
            issues.append(
                Issue(
                    "error",
                    "$.stability.policy",
                    f"stability.policy must be one of {sorted(POLICY_VALUES)}; got {policy!r}",
                )
            )
        audiences = stability.get("audiences")
        if audiences is None:
            issues.append(Issue("warning", "$.stability.audiences", "stability.audiences is recommended"))
        elif not isinstance(audiences, list) or not all(isinstance(a, str) for a in audiences):
            issues.append(Issue("error", "$.stability.audiences", "stability.audiences must be a list of strings"))
        else:
            bad = [a for a in audiences if a not in AUDIENCE_VALUES]
            if bad:
                issues.append(
                    Issue(
                        "error",
                        "$.stability.audiences",
                        f"unknown audiences {bad}; allowed: {sorted(AUDIENCE_VALUES)}",
                    )
                )
            if len(set(audiences)) != len(audiences):
                issues.append(Issue("error", "$.stability.audiences", "stability.audiences must not contain duplicates"))

    streams = data.get("streams")
    if streams is not None:
        if not isinstance(streams, dict):
            issues.append(Issue("error", "$.streams", "streams must be an object"))
        else:
            check_unknown_keys(streams, "streams", "$.streams", issues)
            for key in ("stdout", "stderr"):
                if key in streams and not isinstance(streams[key], str):
                    issues.append(Issue("error", f"$.streams.{key}", f"streams.{key} must be a string"))

    exit_codes = data.get("exit_codes")
    seen_codes: set[int] = set()
    if exit_codes is None:
        issues.append(Issue("warning", "$.exit_codes", "exit_codes table is recommended"))
    elif not isinstance(exit_codes, list):
        issues.append(Issue("error", "$.exit_codes", "exit_codes must be a list"))
    else:
        for i, ec in enumerate(exit_codes):
            p = f"$.exit_codes[{i}]"
            if not isinstance(ec, dict):
                issues.append(Issue("error", p, "entry must be an object"))
                continue
            check_unknown_keys(ec, "exit_code_entry", p, issues)
            code = ec.get("code")
            if not isinstance(code, int) or isinstance(code, bool) or not (0 <= code <= 255):
                issues.append(Issue("error", f"{p}.code", "code must be an integer 0..255"))
            elif code in seen_codes:
                issues.append(Issue("error", f"{p}.code", f"duplicate exit code {code}"))
            else:
                seen_codes.add(code)
            meaning = ec.get("meaning")
            if not isinstance(meaning, str) or not meaning:
                issues.append(Issue("error", f"{p}.meaning", "meaning must be a non-empty string"))

    environment = data.get("environment")
    if environment is not None:
        if not isinstance(environment, dict):
            issues.append(Issue("error", "$.environment", "environment must be an object"))
        else:
            check_unknown_keys(environment, "environment", "$.environment", issues)
            json_flag = environment.get("json_flag")
            if json_flag is not None and not isinstance(json_flag, str):
                issues.append(Issue("error", "$.environment.json_flag", "json_flag must be a string"))
            elif isinstance(json_flag, str) and not is_flag_name(json_flag):
                issues.append(Issue("error", "$.environment.json_flag", f"json_flag {json_flag!r} must look like a flag"))
            respects = environment.get("respects")
            if respects is not None and (not isinstance(respects, list) or not all(isinstance(r, str) for r in respects)):
                issues.append(Issue("error", "$.environment.respects", "respects must be a list of strings"))
            tty = environment.get("tty_aware")
            if tty is not None and not isinstance(tty, bool):
                issues.append(Issue("error", "$.environment.tty_aware", "tty_aware must be a boolean"))

    global_flag_names: set[str] = set()
    global_flags = data.get("global_flags")
    if global_flags is not None:
        if not isinstance(global_flags, list):
            issues.append(Issue("error", "$.global_flags", "global_flags must be a list"))
        else:
            for i, flag in enumerate(global_flags):
                p = f"$.global_flags[{i}]"
                _validate_flag(flag, p, issues)
                if isinstance(flag, dict):
                    n = flag.get("name")
                    if isinstance(n, str):
                        if n in global_flag_names:
                            issues.append(Issue("error", f"{p}.name", f"duplicate global flag {n!r}"))
                        else:
                            global_flag_names.add(n)

    commands = data.get("commands")
    if not isinstance(commands, list):
        issues.append(Issue("error", "$.commands", "commands must be a list"))
        return
    seen_command_names: set[str] = set()
    for i, cmd in enumerate(commands):
        p = f"$.commands[{i}]"
        if not isinstance(cmd, dict):
            issues.append(Issue("error", p, "command must be an object"))
            continue
        check_unknown_keys(cmd, "command", p, issues)
        name = cmd.get("name")
        if not isinstance(name, str) or not name:
            issues.append(Issue("error", f"{p}.name", "name must be a non-empty string"))
        elif not is_ident(name):
            issues.append(Issue("error", f"{p}.name", f"name {name!r} must match {COMMAND_NAME.pattern}"))
        elif name in seen_command_names:
            issues.append(Issue("error", f"{p}.name", f"duplicate command name {name!r}"))
        else:
            seen_command_names.add(name)
        summary = cmd.get("summary")
        if not isinstance(summary, str):
            issues.append(Issue("error", f"{p}.summary", "summary must be a string"))
        _check_since(cmd.get("since"), f"{p}.since", issues)
        _check_stability(cmd.get("stability"), f"{p}.stability", issues)
        if cmd.get("notes") is not None and not isinstance(cmd["notes"], str):
            issues.append(Issue("error", f"{p}.notes", "notes must be a string"))

        for key in ("stdout_format", "stderr_format"):
            v = cmd.get(key)
            if v is not None and v not in STDOUT_FORMATS:
                issues.append(Issue("error", f"{p}.{key}", f"{key} must be one of {sorted(STDOUT_FORMATS)}"))

        cmd_exit = cmd.get("exit_codes")
        if cmd_exit is not None:
            if not isinstance(cmd_exit, list) or not all(isinstance(c, int) and not isinstance(c, bool) for c in cmd_exit):
                issues.append(Issue("error", f"{p}.exit_codes", "exit_codes must be a list of integers"))
            else:
                out_of_range = [c for c in cmd_exit if not (0 <= c <= 255)]
                if out_of_range:
                    issues.append(
                        Issue(
                            "error",
                            f"{p}.exit_codes",
                            f"exit_codes must be in 0..255; got {out_of_range}",
                        )
                    )
                if seen_codes:
                    undefined = [c for c in cmd_exit if c not in seen_codes]
                    if undefined:
                        issues.append(
                            Issue(
                                "warning",
                                f"{p}.exit_codes",
                                f"references exit codes {undefined} that are not in $.exit_codes",
                            )
                        )

        arguments = cmd.get("arguments")
        if arguments is not None:
            if not isinstance(arguments, list):
                issues.append(Issue("error", f"{p}.arguments", "arguments must be a list"))
            else:
                seen_arg_names: set[str] = set()
                last_index = len(arguments) - 1
                for j, arg in enumerate(arguments):
                    ap = f"{p}.arguments[{j}]"
                    if not isinstance(arg, dict):
                        issues.append(Issue("error", ap, "argument must be an object"))
                        continue
                    check_unknown_keys(arg, "argument", ap, issues)
                    an = arg.get("name")
                    if not isinstance(an, str) or not an:
                        issues.append(Issue("error", f"{ap}.name", "argument.name must be a non-empty string"))
                    elif an in seen_arg_names:
                        issues.append(Issue("error", f"{ap}.name", f"duplicate argument name {an!r}"))
                    else:
                        seen_arg_names.add(an)
                    if arg.get("required") is not None and not isinstance(arg["required"], bool):
                        issues.append(Issue("error", f"{ap}.required", "argument.required must be a boolean"))
                    if arg.get("variadic") is True and j != last_index:
                        issues.append(
                            Issue(
                                "error",
                                f"{ap}.variadic",
                                "only the last argument may be variadic",
                            )
                        )
                    if arg.get("variadic") is not None and not isinstance(arg["variadic"], bool):
                        issues.append(Issue("error", f"{ap}.variadic", "argument.variadic must be a boolean"))
                    _check_since(arg.get("since"), f"{ap}.since", issues)

        flags = cmd.get("flags")
        flag_names: set[str] = set()
        if flags is not None:
            if not isinstance(flags, list):
                issues.append(Issue("error", f"{p}.flags", "flags must be a list"))
            else:
                for j, flag in enumerate(flags):
                    fp = f"{p}.flags[{j}]"
                    _validate_flag(flag, fp, issues)
                    if isinstance(flag, dict):
                        n = flag.get("name")
                        if isinstance(n, str):
                            if n in flag_names:
                                issues.append(Issue("error", f"{fp}.name", f"duplicate flag {n!r}"))
                            else:
                                flag_names.add(n)
                            if global_flag_names and n in global_flag_names:
                                issues.append(
                                    Issue(
                                        "warning",
                                        f"{fp}.name",
                                        f"flag {n!r} is also declared in $.global_flags",
                                    )
                                )

        json_output = cmd.get("json_output")
        if json_output is not None:
            if not isinstance(json_output, dict):
                issues.append(Issue("error", f"{p}.json_output", "json_output must be an object"))
            else:
                check_unknown_keys(json_output, "json_output", f"{p}.json_output", issues)
                ss = json_output.get("stable_since")
                if ss is not None and not is_semver(ss):
                    issues.append(
                        Issue(
                            "error",
                            f"{p}.json_output.stable_since",
                            f"stable_since {ss!r} is not a valid semver",
                        )
                    )
                schema = json_output.get("schema")
                if schema is not None and not isinstance(schema, str):
                    issues.append(Issue("error", f"{p}.json_output.schema", "schema must be a string path"))
                notes = json_output.get("notes")
                if notes is not None and not isinstance(notes, str):
                    issues.append(Issue("error", f"{p}.json_output.notes", "notes must be a string"))


def _validate_flag(flag: Any, path: str, issues: list[Issue]) -> None:
    if not isinstance(flag, dict):
        issues.append(Issue("error", path, "flag must be an object"))
        return
    check_unknown_keys(flag, "flag", path, issues)
    n = flag.get("name")
    if not isinstance(n, str) or not n:
        issues.append(Issue("error", f"{path}.name", "flag.name must be a non-empty string"))
    elif not is_flag_name(n):
        issues.append(Issue("error", f"{path}.name", f"flag.name {n!r} must look like --name or -x"))
    short = flag.get("short")
    if short is not None and not is_flag_short(short):
        issues.append(Issue("error", f"{path}.short", f"flag.short {short!r} must be a single -x letter"))
    ftype = flag.get("type")
    if ftype is None:
        issues.append(Issue("error", f"{path}.type", "flag.type is required"))
    elif ftype not in FLAG_TYPES:
        issues.append(
            Issue(
                "error",
                f"{path}.type",
                f"flag.type {ftype!r} must be one of {sorted(FLAG_TYPES)}",
            )
        )
    _check_since(flag.get("since"), f"{path}.since", issues)
    _check_stability(flag.get("stability"), f"{path}.stability", issues)
    if ftype == "enum":
        choices = flag.get("choices")
        if not isinstance(choices, list) or not choices:
            issues.append(Issue("error", f"{path}.choices", "enum flag must have a non-empty choices list"))
        elif not all(isinstance(c, str) for c in choices):
            issues.append(Issue("error", f"{path}.choices", "enum choices must all be strings"))
    if flag.get("required") is not None and not isinstance(flag["required"], bool):
        issues.append(Issue("error", f"{path}.required", "required must be a boolean"))
    if flag.get("description") is not None and not isinstance(flag["description"], str):
        issues.append(Issue("error", f"{path}.description", "description must be a string"))
    if flag.get("default") is not None and ftype is not None:
        _check_default_type(flag["default"], ftype, f"{path}.default", issues)


def _check_since(value: Any, path: str, issues: list[Issue]) -> None:
    if value is None:
        return
    if not is_semver(value):
        issues.append(Issue("error", path, f"version {value!r} is not a valid semver (x.y.z)"))


def _check_stability(value: Any, path: str, issues: list[Issue]) -> None:
    if value is None:
        return
    if value not in STABILITY_VALUES:
        issues.append(
            Issue(
                "error",
                path,
                f"stability {value!r} must be one of {sorted(STABILITY_VALUES)}",
            )
        )


def _check_default_type(value: Any, ftype: str, path: str, issues: list[Issue]) -> None:
    """Best-effort type check for a flag's default value.

    The validator is permissive here: a wrong type is an error because
    silently accepting the wrong shape means a JSON serialiser will
    produce a different value at runtime than the maintainer wrote in
    the contract.
    """
    expected: tuple[type, ...]
    if ftype == "int":
        expected = (int,)
    elif ftype == "float":
        expected = (int, float)  # accept ints where floats are wanted
    elif ftype == "bool":
        expected = (bool,)
    elif ftype in ("string", "path", "enum"):
        expected = (str,)
    elif ftype in ("list", "count"):
        expected = (list, int)
    else:
        return
    if not isinstance(value, expected):
        issues.append(
            Issue(
                "error",
                path,
                f"default {value!r} does not match declared type {ftype!r}",
            )
        )


def _configure_io() -> None:
    """Force UTF-8 on stdout and stderr so a cp1252 console cannot
    traceback on a non-ASCII character in an error message.

    A maintainer's contract may include a non-ASCII policy string
    (`"minor→"`) or a display name with a hyphen, and the
    validator's error message will echo the value back. Without this,
    a Windows console set to cp1252 tracebacks instead of producing a
    readable diagnostic.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def format_text(issues: list[Issue]) -> str:
    if not issues:
        return "OK: contract is valid"
    out: list[str] = []
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    for i in errors:
        out.append(f"ERROR   {i.path}: {i.message}")
    for i in warnings:
        out.append(f"WARNING {i.path}: {i.message}")
    summary = f"{len(errors)} error(s), {len(warnings)} warning(s)"
    out.append("")
    out.append(summary)
    return "\n".join(out)


def main(argv: list[str]) -> int:
    _configure_io()
    parser = argparse.ArgumentParser(description="Validate a CLI contract.json")
    parser.add_argument("path", help="path to contract.json")
    parser.add_argument("--json", action="store_true", help="emit JSON output")
    args = parser.parse_args(argv)

    try:
        with open(args.path, "rb") as f:
            raw = f.read()
    except (OSError, UnicodeError) as exc:
        print(f"ERROR: cannot read {args.path}: {exc}", file=sys.stderr)
        return 2

    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        text = raw.decode("utf-16", errors="replace")
    elif raw.startswith(b"\xef\xbb\xbf"):
        text = raw[3:].decode("utf-8", errors="replace")
    else:
        text = raw.decode("utf-8", errors="replace")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON at {args.path}: {exc}", file=sys.stderr)
        return 2

    issues: list[Issue] = []
    validate(data, issues)
    errors = [i for i in issues if i.severity == "error"]

    if args.json:
        print(json.dumps({"ok": not errors, "issues": [i.to_dict() for i in issues]}, indent=2))
    else:
        print(format_text(issues))

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
