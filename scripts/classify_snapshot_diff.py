#!/usr/bin/env python3
"""Compute a deterministic diff between two snapshot text files.

The classifier produces a unified diff plus a coarse categorization of each
changed line, plus set-difference signals (flag names added or removed
between snapshots, exit codes mentioned on the lines that actually
changed, structural changes when both files parse as JSON). The
contract-review skill uses these as evidence; the semantic "breaking
vs compatible vs cosmetic" call is the skill's job, not this script's.

Exit codes (mirror the POSIX diff convention):
  0  files are identical (line-ending only differences count as identical)
  1  files are different (a diff was produced)
  2  usage error (missing file, invalid args, decode failure)

Usage:
  python3 classify_snapshot_diff.py BEFORE AFTER [--json] [--context N]

Reading:
  Both files are read as bytes and decoded with a BOM-aware decoder.
  UTF-8 with BOM (what Windows editors save) is stripped; UTF-16 with
  BOM (what PowerShell 5.1 redirection produces) is also accepted;
  anything else is decoded as UTF-8 with replacement characters so
  unusual files do not crash the diff. To capture snapshots portably
  in PowerShell, use `Set-Content -Encoding utf8` or `| Out-File
  -Encoding utf8`.

Output:
  The default human-readable form lists changed lines plus three lines of context on each side,
  with `-` / `+` / ` ` markers, followed by a summary of extracted
  signals (flag names added or removed between snapshots, exit codes
  mentioned on the changed lines, JSON structural changes). Pass
  `--json` to get a structured payload instead.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from typing import Any, Optional

# Match a CLI flag with two leading dashes, e.g. --foo, --no-color,
# --dry_run. The trailing boundary accepts any non-identifier punctuation
# we see in real help text (whitespace, comma, equals, brackets, parens,
# backtick, period, pipe, slash, semicolon, end of line). Underscores are
# included in the flag body.
FLAG_RE = re.compile(
    r"(?<![\w-])--[A-Za-z][A-Za-z0-9_-]*"
    r"(?=[\s,=)\]>`'\".:;|/]|$)"
)
# A short flag is a single dash and a single letter, preceded by a flag
# boundary (start of line, whitespace, bracket, paren, equals, quote).
# This filters prose such as "well -known" (the dash run is more than one
# letter) and "3-key" (the dash is preceded by a word character).
SHORT_FLAG_RE = re.compile(
    r"(?:(?<=^)|(?<=[\s\[(,=`'\"]))-([A-Za-z])(?=[\s,=)\]>`'\".:;|/]|$)"
)
# Exit code mention. We only treat a number as an exit code when the line
# also contains one of the conventional markers ("exit", "exits", "code",
# "return", "returns", "status"). Without a marker, the same regex would
# catch prose like "Retry up to 3 on failure" or "Width defaults to 80
# on wide terminals" -- both of which are not exit codes.
EXIT_CODE_MARKER_RE = re.compile(
    r"\b(exit(?:s|ed)?|code|return(?:s|ed)?|status)\b", re.IGNORECASE
)
EXIT_CODE_RE = re.compile(
    r"(?:exit(?:ed|s)?\s*(?:with|code)?\s*[:=]?\s*"
    r"|return(?:s|ed)?\s+"
    r"|status[:=]?\s*)"
    r"(\d{1,3})",
    re.IGNORECASE,
)
# "0 on success, 1 on error" style lists. Like EXIT_CODE_RE, only fires
# when the line also contains an exit-code marker; otherwise the regex
# matches ordinary "3 on failure" prose.
EXIT_CODE_LIST_RE = re.compile(r"\b(\d{1,2})\s+on\s+\w+", re.IGNORECASE)
# Match a JSON key on a {"key": ...} line.
JSON_KEY_RE = re.compile(r'^\s*"([^"\\]*(?:\\.[^"\\]*)*)"\s*:')
# Match the leading line of an option-table row. Used to extract short
# flags only from rows that look like `--flag description` rather than
# from arbitrary prose that happens to contain a dash-letter sequence
# (`jq -c` in an `Examples:` line, `cut -d,` in a recipe, etc.).
OPTION_LINE_RE = re.compile(r"^\s{0,8}(-\S|--\S)")


def extract_flag_names(line: str) -> set[str]:
    """Return the set of flag names mentioned in a line.

    Long flags require two dashes; short flags are extracted only from
    lines that look like an option-table row (leading whitespace then a
    dash). That restriction is what keeps `jq -c` in an `Examples:`
    line from being reported as a candidate `-c` short flag.
    """
    names = {match.group(0) for match in FLAG_RE.finditer(line)}
    if OPTION_LINE_RE.match(line):
        names |= {f"-{m.group(1)}" for m in SHORT_FLAG_RE.finditer(line)}
    return names


def classify_line(line: str) -> set[str]:
    """Return coarse labels for a line. Conservative: may return empty."""
    labels: set[str] = set()
    if extract_flag_names(line):
        labels.add("flag")
    if JSON_KEY_RE.match(line):
        labels.add("json-key")
    has_exit_marker = bool(EXIT_CODE_MARKER_RE.search(line))
    if has_exit_marker:
        for m in EXIT_CODE_RE.finditer(line):
            labels.add(f"exit-code:{m.group(1)}")
        for m in EXIT_CODE_LIST_RE.finditer(line):
            labels.add(f"exit-code:{m.group(1)}")
    if line.lstrip().startswith(("{", "}", "[", "]")):
        labels.add("json-brace")
    if line.lstrip().startswith("#"):
        labels.add("comment")
    return labels


def compute_diff(
    before_lines: list[str],
    after_lines: list[str],
    context: int,
    before_offset: int = 0,
    after_offset: int = 0,
) -> list[dict[str, Any]]:
    """Return a list of change records. Each record:
       {op: "added"|"removed"|"context", line: str, no: int, labels: [...]}

    `before_offset` and `after_offset` shift the line numbers in the
    output: pass the number of lines that come before this section in
    the source file. The contract-review skill quotes evidence "with
    line numbers", so those numbers have to be file-relative when the
    snapshot uses the structured convention.

    Context records far from any change are dropped so a large help
    file does not flood the diff. The drop keeps `context` context
    lines around every change. A non-contiguous gap between two
    surviving windows inserts a `...` separator record so the
    reviewer can see that lines were omitted.
    """
    sm = difflib.SequenceMatcher(a=before_lines, b=after_lines, autojunk=False)
    records: list[dict[str, Any]] = []

    def clean(line: str) -> str:
        # Drop the trailing newline that callers may include; the records are
        # meant to be human-readable lines, not raw bytes.
        if line.endswith("\r\n"):
            return line[:-2]
        if line.endswith("\n") or line.endswith("\r"):
            return line[:-1]
        return line

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i1, i2):
                text = clean(before_lines[k])
                records.append(
                    {
                        "op": "context",
                        "before_no": before_offset + k + 1,
                        "after_no": after_offset + j1 + (k - i1) + 1,
                        "line": text,
                        "labels": sorted(classify_line(text)),
                    }
                )
        elif tag == "replace":
            before_block = before_lines[i1:i2]
            after_block = after_lines[j1:j2]
            max_len = max(len(before_block), len(after_block))
            for k in range(max_len):
                if k < len(before_block):
                    text = clean(before_block[k])
                    records.append(
                        {
                            "op": "removed",
                            "before_no": before_offset + i1 + k + 1,
                            "line": text,
                            "labels": sorted(classify_line(text)),
                        }
                    )
                if k < len(after_block):
                    text = clean(after_block[k])
                    records.append(
                        {
                            "op": "added",
                            "after_no": after_offset + j1 + k + 1,
                            "line": text,
                            "labels": sorted(classify_line(text)),
                        }
                    )
        elif tag == "delete":
            for k in range(i1, i2):
                text = clean(before_lines[k])
                records.append(
                    {
                        "op": "removed",
                        "before_no": before_offset + k + 1,
                        "line": text,
                        "labels": sorted(classify_line(text)),
                    }
                )
        elif tag == "insert":
            for k in range(j1, j2):
                text = clean(after_lines[k])
                records.append(
                    {
                        "op": "added",
                        "after_no": after_offset + k + 1,
                        "line": text,
                        "labels": sorted(classify_line(text)),
                    }
                )
    return trim_context(records, context)


def trim_context(records: list[dict[str, Any]], context: int) -> list[dict[str, Any]]:
    """Drop context records that are more than `context` lines from a change.

    A non-contiguous gap between two surviving windows gets a
    `...` separator record so the reader can see that lines were
    omitted.
    """
    if context < 0 or not records:
        return records
    keep = [False] * len(records)
    last_change = -1
    for idx, r in enumerate(records):
        if r["op"] != "context":
            for k in range(max(0, idx - context), min(len(records), idx + context + 1)):
                keep[k] = True
            last_change = idx
    if last_change == -1:
        return records
    out: list[dict[str, Any]] = []
    prev_idx = -2
    for i, (r, k) in enumerate(zip(records, keep)):
        if not k:
            continue
        if out and i > prev_idx + 1:
            out.append({"op": "context", "line": "...", "labels": ["separator"]})
        out.append(r)
        prev_idx = i
    return out


def diff_json(before: Any, after: Any, path: str = "") -> list[dict[str, Any]]:
    """Compute a structural diff between two parsed JSON values.

    Returns one record per changed leaf, with a JSON-pointer-style path.
    The classifier exposes this when both files parse as JSON; the text
    diff still runs, but the structured signals carry the information a
    reviewer needs about key removals, type changes, and value changes.

    Deeply nested JSON (more than a few hundred levels) trips Python's
    recursion limit; the caller should not run the diff on adversarial
    input. The depth limit below stops recursion well before Python
    itself does, so the diff finishes even on pathological input; a
    path deeper than the limit is reported as a single "too_deep"
    record.
    """
    changes: list[dict[str, Any]] = []
    label = path or "/"
    # Stop well below Python's own recursion limit (default ~1000). Real
    # JSON snapshots are nowhere near this depth; the limit exists for
    # adversarial or generated input.
    MAX_DEPTH = min(200, max(50, sys.getrecursionlimit() // 5))

    def walk(b: Any, a: Any, p: str, depth: int) -> None:
        if depth > MAX_DEPTH:
            changes.append({"path": p or "/", "change": "too_deep"})
            return
        if type(b) is not type(a):
            changes.append({
                "path": p or "/", "change": "type_changed",
                "before_type": type(b).__name__,
                "after_type": type(a).__name__,
            })
            return
        if isinstance(b, dict):
            for key in b:
                if key not in a:
                    changes.append({"path": f"{p}.{key}" if p else f"/{key}", "change": "removed", "before": b[key]})
            for key in a:
                if key not in b:
                    changes.append({"path": f"{p}.{key}" if p else f"/{key}", "change": "added", "after": a[key]})
            for key in b:
                if key in a:
                    walk(b[key], a[key], f"{p}.{key}" if p else f"/{key}", depth + 1)
        elif isinstance(b, list):
            if len(b) != len(a):
                changes.append({
                    "path": p or "/", "change": "length_changed",
                    "before_len": len(b), "after_len": len(a),
                })
            for i, (bv, av) in enumerate(zip(b, a)):
                walk(bv, av, f"{p}[{i}]", depth + 1)
        elif b != a:
            changes.append({"path": p or "/", "change": "value_changed", "before": b, "after": a})

    walk(before, after, path, 0)
    return changes


def summarize(
    records: list[dict[str, Any]],
    json_changes: Optional[list[dict[str, Any]]] = None,
    before_snapshot: Optional[dict[str, Any]] = None,
    after_snapshot: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Compute the per-classification signals from the text diff records.

    Flag names are computed over the entire stdout of each snapshot, not
    just the changed lines, so a deleted Examples line that mentions a
    flag does not produce a false "removed" signal (the flag may still
    appear in the option table). Exit codes are taken from the changed
    lines that carry the exit-code label; the structured snapshot's
    `--- exit N` field contributes a separate signal so a code change
    that the help text does not mention is still visible.
    """
    before_flags = _flags_in_lines(before_snapshot["stdout"]) if before_snapshot else set()
    after_flags = _flags_in_lines(after_snapshot["stdout"]) if after_snapshot else set()

    exit_codes_added: set[str] = set()
    exit_codes_removed: set[str] = set()
    for r in records:
        for lbl in r["labels"]:
            if not lbl.startswith("exit-code:"):
                continue
            if r["op"] == "added":
                exit_codes_added.add(lbl)
            elif r["op"] == "removed":
                exit_codes_removed.add(lbl)

    if before_snapshot and after_snapshot:
        b_exit = before_snapshot.get("exit_code")
        a_exit = after_snapshot.get("exit_code")
        if b_exit is not None and a_exit is not None and b_exit != a_exit:
            exit_codes_removed.add(f"exit-code:{b_exit}")
            exit_codes_added.add(f"exit-code:{a_exit}")

    added_count = sum(1 for r in records if r["op"] == "added")
    removed_count = sum(1 for r in records if r["op"] == "removed")

    flags_added = sorted(after_flags - before_flags)
    flags_removed = sorted(before_flags - after_flags)
    flags_present_on_both_sides = sorted(before_flags & after_flags)

    summary: dict[str, Any] = {
        "added_lines": added_count,
        "removed_lines": removed_count,
        "context_lines": sum(1 for r in records if r["op"] == "context"),
        "flags_added": flags_added,
        "flags_removed": flags_removed,
        "flags_present_on_both_sides": flags_present_on_both_sides,
        "exit_codes_added": sorted(exit_codes_added - exit_codes_removed),
        "exit_codes_removed": sorted(exit_codes_removed - exit_codes_added),
    }
    if json_changes is not None:
        summary["json_changes"] = json_changes
    if before_snapshot and after_snapshot:
        summary["before_command"] = before_snapshot.get("command")
        summary["after_command"] = after_snapshot.get("command")
    return summary


def _flags_in_lines(lines: list[str]) -> set[str]:
    """Collect every flag name mentioned anywhere in `lines`.

    Iterating the whole snapshot (instead of only changed lines) keeps
    the flag sets stable across cosmetic reflows and across deletions
    of prose that mentions a flag without removing the flag itself.
    """
    names: set[str] = set()
    for line in lines:
        names |= extract_flag_names(line)
    return names


def _line_ending_note(before_path: str, after_path: str) -> str:
    """Return a short note when two byte-identical-content files differ
    only in line endings, so the IDENTITY message can tell the reader."""
    try:
        with open(before_path, "rb") as f:
            before = f.read()
        with open(after_path, "rb") as f:
            after = f.read()
    except OSError:
        return ""
    if before == after:
        return ""
    if before.replace(b"\r\n", b"\n") == after.replace(b"\r\n", b"\n"):
        before_kind = "CRLF" if b"\r\n" in before else ("CR" if b"\r" in before else "LF")
        after_kind = "CRLF" if b"\r\n" in after else ("CR" if b"\r" in after else "LF")
        return f"line endings differ: {before_kind} vs {after_kind}"
    return ""


def format_text(records: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    out: list[str] = []
    out.append(f"--- diff ({summary['added_lines']} added, {summary['removed_lines']} removed)")
    for r in records:
        prefix = {"added": "+", "removed": "-", "context": " "}.get(r["op"], " ")
        no = r.get("after_no") or r.get("before_no") or 0
        labels = "  ".join("[" + l + "]" for l in r["labels"]) if r["labels"] else ""
        line_text = r["line"].rstrip()
        suffix = ("  " + labels) if labels else ""
        if no:
            out.append(f"{prefix}{no:4d} {line_text}{suffix}")
        else:
            out.append(f"{prefix}     {line_text}{suffix}")
    out.append("")
    out.append("--- signals (these are evidence, not a verdict)")
    if summary.get("before_command") or summary.get("after_command"):
        out.append(f"  before command: {summary.get('before_command')}")
        out.append(f"  after command:  {summary.get('after_command')}")
    if summary["flags_added"]:
        out.append("  flags added:    " + str(summary["flags_added"]))
    if summary["flags_removed"]:
        out.append("  flags removed:  " + str(summary["flags_removed"]))
    if summary["flags_present_on_both_sides"]:
        out.append(
            "  flags present on both sides (read the diff; a default, type or choices change still hides here): "
            + str(summary["flags_present_on_both_sides"])
        )
    if summary["exit_codes_added"]:
        out.append("  exit codes added:   " + str(summary["exit_codes_added"]))
    if summary["exit_codes_removed"]:
        out.append("  exit codes removed: " + str(summary["exit_codes_removed"]))
    if summary.get("json_changes"):
        out.append("  json structural changes:")
        for c in summary["json_changes"]:
            out.append("    " + str(c["change"]).ljust(14) + " " + str(c["path"]))
    return "\n".join(out)


def load_lines(path: str) -> list[str]:
    """Read a snapshot file as text.

    The file is opened in binary mode so we can detect the BOM ourselves
    rather than relying on Windows locale guessing. UTF-8 with BOM (the
    Windows `utf-8` encoding in Python) becomes plain UTF-8; UTF-16 with
    a BOM is also handled. Anything else is decoded as UTF-8 with
    replacement so the diff still runs on unusual files instead of
    crashing.
    """
    with open(path, "rb") as f:
        raw = f.read()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        text = raw.decode("utf-16", errors="replace")
    elif raw.startswith(b"\xef\xbb\xbf"):
        text = raw[3:].decode("utf-8", errors="replace")
    else:
        text = raw.decode("utf-8", errors="replace")
    return text.splitlines(keepends=False)


CMD_HEADER_RE = re.compile(r"^\$\s+(.+)$")
SECTION_HEADER_RE = re.compile(r"^---\s+(stderr|exit(?:\s+(\d+))?)\s*$")


def parse_snapshot(lines: list[str]) -> dict[str, Any]:
    """Split a snapshot file into stdout, stderr, and exit-code sections.

    The optional convention is:

      $ mytool list --json
      <stdout lines>

      --- stderr
      <stderr lines>

      --- exit 0

    Files that do not start with a `$ ...` header are treated as plain
    stdout (backwards compatible with the simple "capture --help" workflow).
    """
    if not lines or not CMD_HEADER_RE.match(lines[0]):
        return {
            "command": None,
            "stdout": lines,
            "stderr": [],
            "exit_code": None,
            "structured": False,
        }

    command = CMD_HEADER_RE.match(lines[0]).group(1).strip()
    stdout: list[str] = []
    stderr: list[str] = []
    exit_code: Optional[int] = None
    current = "stdout"
    for raw in lines[1:]:
        m = SECTION_HEADER_RE.match(raw)
        if m:
            if m.group(1) == "stderr":
                current = "stderr"
            else:
                current = "exit"
                code_str = (m.group(2) or "").strip()
                if code_str.isdigit():
                    exit_code = int(code_str)
            continue
        if current == "stdout":
            stdout.append(raw)
        elif current == "stderr":
            stderr.append(raw)

    return {
        "command": command,
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "structured": True,
    }


def configure_io() -> None:
    """Force UTF-8 on stdout and stderr.

    On Windows the default console code page is often cp1252, which cannot
    represent common help-text characters (em dashes, arrows, box drawing).
    A traceback in that situation is the worst possible outcome: the
    caller sees an error and not the diff they asked for.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                # Stream may already be closed or non-reconfigurable.
                pass


def main(argv: list[str]) -> int:
    configure_io()
    parser = argparse.ArgumentParser(description="Diff two snapshot files")
    parser.add_argument("before", help="path to the old snapshot")
    parser.add_argument("after", help="path to the new snapshot")
    parser.add_argument("--json", action="store_true", help="emit JSON output")
    parser.add_argument(
        "--context",
        type=int,
        default=3,
        help="context lines around each change (default: 3). Negative values are an error.",
    )
    args = parser.parse_args(argv)

    if args.context < 0:
        print(f"ERROR: --context must be >= 0; got {args.context}", file=sys.stderr)
        return 2

    try:
        before_lines = load_lines(args.before)
        after_lines = load_lines(args.after)
    except (OSError, UnicodeError) as exc:
        print(f"ERROR: cannot read snapshot: {exc}", file=sys.stderr)
        return 2

    before_snap = parse_snapshot(before_lines)
    after_snap = parse_snapshot(after_lines)

    if (
        before_snap["stdout"] == after_snap["stdout"]
        and before_snap["stderr"] == after_snap["stderr"]
        and before_snap["exit_code"] == after_snap["exit_code"]
        and before_snap["command"] == after_snap["command"]
    ):
        line_ending_note = _line_ending_note(args.before, args.after)
        if args.json:
            print(json.dumps({
                "identical": True,
                "line_ending_note": line_ending_note,
                "summary": summarize([], None, before_snap, after_snap),
            }, indent=2))
        else:
            msg = "IDENTICAL: no differences between the two snapshots"
            if line_ending_note:
                msg += f" ({line_ending_note})"
            print(msg)
        return 0

    # When the snapshot is structured, line numbers must refer to the
    # source file, not to the section. stdout starts at line 2 (line 1
    # is the `$ cmd` header). stderr starts after stdout and the
    # `--- stderr` marker line. Plain-text snapshots have a 0 offset.
    stdout_offset_before = 1 if before_snap["structured"] else 0
    stdout_offset_after = 1 if after_snap["structured"] else 0
    records = compute_diff(
        before_snap["stdout"],
        after_snap["stdout"],
        args.context,
        before_offset=stdout_offset_before,
        after_offset=stdout_offset_after,
    )
    stderr_records: list[dict[str, Any]] = []
    if before_snap["structured"] or after_snap["structured"]:
        stderr_offset_before = stdout_offset_before + len(before_snap["stdout"]) + 1
        stderr_offset_after = stdout_offset_after + len(after_snap["stdout"]) + 1
        stderr_records = compute_diff(
            before_snap["stderr"],
            after_snap["stderr"],
            args.context,
            before_offset=stderr_offset_before,
            after_offset=stderr_offset_after,
        )
        if stderr_records:
            records.append({"op": "context", "line": "--- stderr", "labels": []})
            records.extend(stderr_records)

    json_changes: Optional[list[dict[str, Any]]] = None
    try:
        before_json_text = "\n".join(before_snap["stdout"]) or "{}"
        after_json_text = "\n".join(after_snap["stdout"]) or "{}"
        before_json = json.loads(before_json_text)
        after_json = json.loads(after_json_text)
        json_changes = diff_json(before_json, after_json)
    except (ValueError, TypeError):
        json_changes = None

    summary = summarize(records, json_changes, before_snap, after_snap)

    if args.json:
        out = {
            "identical": False,
            "summary": summary,
            "records": records,
        }
        print(json.dumps(out, indent=2, default=str))
    else:
        print(format_text(records, summary))

    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
