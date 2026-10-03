"""Tests for classify_snapshot_diff.py.

Run via
    python tests/run_tests.py
or
    python -m unittest tests.test_classify_snapshot_diff
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "classify_snapshot_diff.py"
FIXTURES = HERE / "fixtures"
sys.path.insert(0, str(HERE.parent / "scripts"))
import classify_snapshot_diff  # noqa: E402


class TestClassifyLine(unittest.TestCase):
    def test_flag_match(self) -> None:
        labels = classify_snapshot_diff.classify_line("  --foo, --bar, --baz  ")
        self.assertIn("flag", labels)

    def test_short_flag_match(self) -> None:
        labels = classify_snapshot_diff.classify_line("  -n, --limit <N>")
        self.assertIn("flag", labels)

    def test_tolerant_flag_match_equals(self) -> None:
        # --output=FILE is a real pattern in help text; the regex must catch it.
        labels = classify_snapshot_diff.classify_line("--output=FILE")
        self.assertIn("flag", labels)

    def test_tolerant_flag_match_brackets(self) -> None:
        labels = classify_snapshot_diff.classify_line("[--verbose]")
        self.assertIn("flag", labels)

    def test_tolerant_flag_match_backtick(self) -> None:
        labels = classify_snapshot_diff.classify_line("`--json`")
        self.assertIn("flag", labels)

    def test_tolerant_flag_match_paren(self) -> None:
        labels = classify_snapshot_diff.classify_line("(--json)")
        self.assertIn("flag", labels)

    def test_tolerant_flag_match_period(self) -> None:
        labels = classify_snapshot_diff.classify_line("See --json.")
        self.assertIn("flag", labels)

    def test_prose_with_internal_dash_does_not_match(self) -> None:
        # "well -known" should not be flagged: the dash run is short and not
        # at a word boundary the way a real flag would be.
        labels = classify_snapshot_diff.classify_line("this is well -known")
        self.assertNotIn("flag", labels)

    def test_json_key_match(self) -> None:
        labels = classify_snapshot_diff.classify_line('    "items": [')
        self.assertIn("json-key", labels)

    def test_no_match(self) -> None:
        labels = classify_snapshot_diff.classify_line("plain prose with no markers")
        self.assertEqual(labels, set())

    def test_exit_code_match(self) -> None:
        labels = classify_snapshot_diff.classify_line("Exit code: 2 on usage error.")
        self.assertIn("exit-code:2", labels)

    def test_multiple_exit_codes_on_one_line(self) -> None:
        labels = classify_snapshot_diff.classify_line(
            "Exit code: 0 on success, 1 on error, 2 on usage error."
        )
        self.assertIn("exit-code:0", labels)
        self.assertIn("exit-code:1", labels)
        self.assertIn("exit-code:2", labels)

    def test_comment_label(self) -> None:
        labels = classify_snapshot_diff.classify_line("# this is a comment")
        self.assertIn("comment", labels)


class TestExtractFlagNames(unittest.TestCase):
    def test_basic(self) -> None:
        self.assertEqual(
            classify_snapshot_diff.extract_flag_names("  --foo, --bar  "),
            {"--foo", "--bar"},
        )

    def test_short_and_long(self) -> None:
        self.assertEqual(
            classify_snapshot_diff.extract_flag_names("-n, --limit <N>"),
            {"-n", "--limit"},
        )

    def test_brackets_and_punctuation(self) -> None:
        self.assertEqual(
            classify_snapshot_diff.extract_flag_names("[--verbose] (--json) `--quiet`"),
            {"--verbose", "--json", "--quiet"},
        )

    def test_equals(self) -> None:
        self.assertEqual(
            classify_snapshot_diff.extract_flag_names("--output=FILE"),
            {"--output"},
        )

    def test_prose_internal_dash_filtered(self) -> None:
        # "well -known thing" must not surface "-known" as a flag.
        self.assertEqual(
            classify_snapshot_diff.extract_flag_names("well -known thing"),
            set(),
        )

    def test_hyphenated_word_filtered(self) -> None:
        # "well-known" is a single hyphenated word; neither - nor -known
        # should be reported as a flag.
        self.assertEqual(
            classify_snapshot_diff.extract_flag_names("a well-known thing"),
            set(),
        )

    def test_short_flag_requires_boundary(self) -> None:
        # A short flag is only extracted from an option-table row. Prose
        # like "see -v for verbose" must not surface -v: the line does
        # not start with a dash, it starts with "see".
        self.assertEqual(
            classify_snapshot_diff.extract_flag_names("see -v for verbose"),
            set(),
        )

    def test_short_flag_on_option_line(self) -> None:
        # An option-table row does extract its short flag.
        self.assertEqual(
            classify_snapshot_diff.extract_flag_names("  -v, --verbose"),
            {"-v", "--verbose"},
        )

    def test_short_flag_not_extracted_from_examples(self) -> None:
        # The shape of an Examples line starts with the command name,
        # not a dash, so `jq -c` is not a candidate short flag.
        self.assertEqual(
            classify_snapshot_diff.extract_flag_names("  tasks list --format ndjson | jq -c '.id'"),
            {"--format"},
        )

    def test_indented_long_flag(self) -> None:
        self.assertEqual(
            classify_snapshot_diff.extract_flag_names("    --json"),
            {"--json"},
        )


class TestComputeDiff(unittest.TestCase):
    def test_identical_inputs_yield_no_records(self) -> None:
        before = ["one\n", "two\n", "three\n"]
        records = classify_snapshot_diff.compute_diff(before, list(before), context=3)
        # All context, none are interesting changes
        self.assertTrue(all(r["op"] == "context" for r in records))

    def test_added_line(self) -> None:
        before = ["a\n", "c\n"]
        after = ["a\n", "b\n", "c\n"]
        records = classify_snapshot_diff.compute_diff(before, after, context=0)
        added = [r for r in records if r["op"] == "added"]
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]["line"], "b")
        self.assertEqual(added[0]["after_no"], 2)

    def test_removed_line(self) -> None:
        before = ["a\n", "b\n", "c\n"]
        after = ["a\n", "c\n"]
        records = classify_snapshot_diff.compute_diff(before, after, context=0)
        removed = [r for r in records if r["op"] == "removed"]
        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0]["line"], "b")
        self.assertEqual(removed[0]["before_no"], 2)

    def test_pure_delete_line_number(self) -> None:
        # Regression for the line-number doubling bug: a pure delete away
        # from the top of the file must report before_no == the deleted
        # line's actual position.
        before = [f"line {i}\n" for i in range(1, 11)]
        after = before[:7] + before[8:]
        records = classify_snapshot_diff.compute_diff(before, after, context=0)
        removed = [r for r in records if r["op"] == "removed"]
        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0]["before_no"], 8)
        self.assertEqual(removed[0]["line"], "line 8")

    def test_pure_insert_line_number(self) -> None:
        before = [f"line {i}\n" for i in range(1, 11)]
        after = before[:5] + ["NEW\n"] + before[5:]
        records = classify_snapshot_diff.compute_diff(before, after, context=0)
        added = [r for r in records if r["op"] == "added"]
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]["after_no"], 6)
        self.assertEqual(added[0]["line"], "NEW")

    def test_replaced_block(self) -> None:
        before = ["alpha\n", "beta\n"]
        after = ["ALPHA\n", "BETA\n", "GAMMA\n"]
        records = classify_snapshot_diff.compute_diff(before, after, context=0)
        added = [r for r in records if r["op"] == "added"]
        removed = [r for r in records if r["op"] == "removed"]
        self.assertEqual(len(added), 3)
        self.assertEqual(len(removed), 2)


class TestSummarize(unittest.TestCase):
    def _snap(self, stdout, **overrides):
        return {
            "command": overrides.get("command"),
            "stdout": stdout,
            "stderr": overrides.get("stderr", []),
            "exit_code": overrides.get("exit_code"),
            "structured": False,
        }

    def test_summary_counts(self) -> None:
        before = self._snap(["  --foo  bar\n"])
        after = self._snap(["  --baz  qux\n"])
        records = classify_snapshot_diff.compute_diff(before["stdout"], after["stdout"], context=0)
        summary = classify_snapshot_diff.summarize(records, None, before, after)
        self.assertEqual(summary["added_lines"], 1)
        self.assertEqual(summary["removed_lines"], 1)
        self.assertEqual(summary["flags_added"], ["--baz"])
        self.assertEqual(summary["flags_removed"], ["--foo"])

    def test_summary_dedupes_flags_that_only_changed_padding(self) -> None:
        # Column padding alone is reported as present-on-both-sides, not
        # as add/remove. The label no longer claims "padding only" because
        # a default or type change would hide in this set.
        before = self._snap(["  --json  Emit JSON\n"])
        after = self._snap(["  --json      Emit JSON\n"])
        records = classify_snapshot_diff.compute_diff(before["stdout"], after["stdout"], context=0)
        summary = classify_snapshot_diff.summarize(records, None, before, after)
        self.assertEqual(summary["flags_added"], [])
        self.assertEqual(summary["flags_removed"], [])
        self.assertEqual(summary["flags_present_on_both_sides"], ["--json"])

    def test_summary_uses_whole_snapshot_for_flag_sets(self) -> None:
        # The reviewer noted that deleting a line that mentions a flag
        # in prose used to mark the flag as removed, even when the flag
        # itself was still in the option table. The fix: compute the
        # flag sets from the whole snapshot, not from changed lines.
        before = self._snap([
            "Options:",
            "  --json     JSON output",
            "  --quiet    Quiet mode",
            "",
            "Examples:",
            "  mytool --json | jq",
        ])
        after = self._snap([
            "Options:",
            "  --json     JSON output",
        ])
        records = classify_snapshot_diff.compute_diff(before["stdout"], after["stdout"], context=0)
        summary = classify_snapshot_diff.summarize(records, None, before, after)
        self.assertNotIn("--json", summary["flags_removed"])
        self.assertEqual(summary["flags_removed"], ["--quiet"])
        self.assertEqual(summary["flags_added"], [])
        self.assertEqual(summary["flags_present_on_both_sides"], ["--json"])

    def test_summary_picks_up_exit_codes(self) -> None:
        before = ["Exit code: 1 on error.\n"]
        after = ["Exit code: 2 on error.\n"]
        records = classify_snapshot_diff.compute_diff(before, after, context=0)
        summary = classify_snapshot_diff.summarize(records)
        self.assertIn("exit-code:2", summary["exit_codes_added"])
        self.assertIn("exit-code:1", summary["exit_codes_removed"])

    def test_summary_picks_up_all_codes_on_multi_code_line(self) -> None:
        before = ["Exit code: 0 on success, 1 on error.\n"]
        after = ["Exit code: 0 on success, 1 on error, 2 on usage error.\n"]
        records = classify_snapshot_diff.compute_diff(before, after, context=0)
        summary = classify_snapshot_diff.summarize(records)
        self.assertIn("exit-code:2", summary["exit_codes_added"])


class TestDiffJson(unittest.TestCase):
    def test_deep_json_does_not_recursion_error(self) -> None:
        # Adversarial input would crash with RecursionError before the
        # depth limit was added. Build a 2000-deep list and confirm the
        # diff still runs.
        deep = "x"
        for _ in range(2000):
            deep = [deep]
        before = deep
        after = deep
        changes = classify_snapshot_diff.diff_json(before, after)
        # The depth limit was reached; the changes list contains at
        # least one "too_deep" record and no Python exception was raised.
        self.assertTrue(any(c.get("change") == "too_deep" for c in changes))

    def test_key_added(self) -> None:
        before = {"a": 1}
        after = {"a": 1, "b": 2}
        changes = classify_snapshot_diff.diff_json(before, after)
        paths = [c["path"] for c in changes]
        self.assertIn("/b", paths)
        self.assertEqual([c for c in changes if c["path"] == "/b"][0]["change"], "added")

    def test_key_removed(self) -> None:
        before = {"a": 1, "b": 2}
        after = {"a": 1}
        changes = classify_snapshot_diff.diff_json(before, after)
        paths = [c["path"] for c in changes]
        self.assertIn("/b", paths)
        self.assertEqual([c for c in changes if c["path"] == "/b"][0]["change"], "removed")

    def test_type_changed(self) -> None:
        before = {"a": "1"}
        after = {"a": 1}
        changes = classify_snapshot_diff.diff_json(before, after)
        types = [c for c in changes if c["change"] == "type_changed"]
        self.assertEqual(len(types), 1)
        self.assertEqual(types[0]["before_type"], "str")
        self.assertEqual(types[0]["after_type"], "int")

    def test_nested(self) -> None:
        before = {"items": [{"id": 1, "name": "x"}]}
        after = {"items": [{"id": 1, "name": "x", "tags": ["a"]}]}
        changes = classify_snapshot_diff.diff_json(before, after)
        paths = [c["path"] for c in changes]
        self.assertIn("/items[0].tags", paths)

    def test_value_changed(self) -> None:
        before = {"a": 1}
        after = {"a": 2}
        changes = classify_snapshot_diff.diff_json(before, after)
        vals = [c for c in changes if c["change"] == "value_changed"]
        self.assertEqual(len(vals), 1)
        self.assertEqual(vals[0]["before"], 1)
        self.assertEqual(vals[0]["after"], 2)

    def test_array_length_changed(self) -> None:
        before = {"items": [1, 2]}
        after = {"items": [1, 2, 3]}
        changes = classify_snapshot_diff.diff_json(before, after)
        lens = [c for c in changes if c["change"] == "length_changed"]
        self.assertEqual(len(lens), 1)
        self.assertEqual(lens[0]["before_len"], 2)
        self.assertEqual(lens[0]["after_len"], 3)


class TestParseSnapshot(unittest.TestCase):
    def test_plain_text_is_stdout(self) -> None:
        snap = classify_snapshot_diff.parse_snapshot(["Usage: foo", "Options:"])
        self.assertFalse(snap["structured"])
        self.assertEqual(snap["stdout"], ["Usage: foo", "Options:"])
        self.assertEqual(snap["stderr"], [])
        self.assertIsNone(snap["exit_code"])

    def test_command_header(self) -> None:
        snap = classify_snapshot_diff.parse_snapshot([
            "$ mytool list --json",
            "first line of stdout",
        ])
        self.assertTrue(snap["structured"])
        self.assertEqual(snap["command"], "mytool list --json")
        self.assertEqual(snap["stdout"], ["first line of stdout"])

    def test_stderr_section(self) -> None:
        snap = classify_snapshot_diff.parse_snapshot([
            "$ mytool build",
            "compiling...",
            "--- stderr",
            "warning: deprecated flag",
        ])
        self.assertEqual(snap["stdout"], ["compiling..."])
        self.assertEqual(snap["stderr"], ["warning: deprecated flag"])

    def test_exit_section(self) -> None:
        snap = classify_snapshot_diff.parse_snapshot([
            "$ mytool list",
            "items",
            "--- exit 2",
        ])
        self.assertEqual(snap["stdout"], ["items"])
        self.assertEqual(snap["exit_code"], 2)

    def test_full_convention(self) -> None:
        snap = classify_snapshot_diff.parse_snapshot([
            "$ mytool list --json",
            '{"items": []}',
            "",
            "--- stderr",
            "WARN something",
            "--- exit 1",
        ])
        self.assertEqual(snap["command"], "mytool list --json")
        self.assertEqual(snap["stdout"], ['{"items": []}', ""])
        self.assertEqual(snap["stderr"], ["WARN something"])
        self.assertEqual(snap["exit_code"], 1)


class TestSummarizeExitCodeSection(unittest.TestCase):
    def test_exit_code_change_is_signalled(self) -> None:
        # Two structured snapshots whose only difference is the exit code
        # must report the change in exit_codes_added/removed.
        before = {"command": "x", "stdout": [], "stderr": [], "exit_code": 0, "structured": True}
        after = {"command": "x", "stdout": [], "stderr": [], "exit_code": 2, "structured": True}
        summary = classify_snapshot_diff.summarize([], None, before, after)
        self.assertIn("exit-code:2", summary["exit_codes_added"])
        self.assertIn("exit-code:0", summary["exit_codes_removed"])

    def test_command_change_is_reported(self) -> None:
        before = {"command": "x --foo", "stdout": [], "stderr": [], "exit_code": 0, "structured": True}
        after = {"command": "x --bar", "stdout": [], "stderr": [], "exit_code": 0, "structured": True}
        summary = classify_snapshot_diff.summarize([], None, before, after)
        self.assertEqual(summary["before_command"], "x --foo")
        self.assertEqual(summary["after_command"], "x --bar")


class TestLineEndingNote(unittest.TestCase):
    def test_crlf_vs_lf_is_announced(self) -> None:
        # Two files with the same content but different line endings
        # compare as identical; the message should say so.
        import tempfile, os
        with tempfile.NamedTemporaryFile("wb", delete=False, suffix=".txt") as f:
            f.write(b"alpha\nbeta\n")
            b = f.name
        with tempfile.NamedTemporaryFile("wb", delete=False, suffix=".txt") as f:
            f.write(b"alpha\r\nbeta\r\n")
            a = f.name
        try:
            result = subprocess.run(
                [sys.executable, str(SCRIPT), b, a],
                capture_output=True, text=True, cwd=str(HERE.parent),
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("IDENTICAL", result.stdout)
            self.assertIn("line endings differ", result.stdout)
        finally:
            os.unlink(b); os.unlink(a)


class TestStderrSection(unittest.TestCase):
    def test_stderr_change_is_visible(self) -> None:
        # The two fixtures only differ in their stderr text. The stdout
        # text is identical, so an identical-file check would be wrong;
        # the exit code also differs (0 vs 1) and must surface.
        result = subprocess.run(
            [sys.executable, str(SCRIPT),
             str(FIXTURES / "snapshot-stdout.txt"),
             str(FIXTURES / "snapshot-stderr-only.txt")],
            capture_output=True, text=True, cwd=str(HERE.parent),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("WARN: deprecated flag --bar", result.stdout)
        self.assertIn("ERROR: connection refused", result.stdout)
        # exit-code signal should report 0 -> 1.
        self.assertIn("exit-code:1", result.stdout)
        self.assertIn("exit-code:0", result.stdout)


class TestCliInvocation(unittest.TestCase):
    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            cwd=str(HERE.parent),
        )

    def test_identical_files_exit_zero(self) -> None:
        # The classifier now mirrors POSIX `diff`: 0 = identical, 1 = different,
        # 2 = error. This is what CI scripts already know how to read.
        result = self._run(
            str(FIXTURES / "snapshot-v1.txt"),
            str(FIXTURES / "snapshot-v1.txt"),
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("IDENTICAL", result.stdout)

    def test_different_files_exit_one(self) -> None:
        result = self._run(
            str(FIXTURES / "snapshot-v1.txt"),
            str(FIXTURES / "snapshot-v2.txt"),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("--- diff", result.stdout)

    def test_json_output_is_parseable(self) -> None:
        result = self._run(
            str(FIXTURES / "snapshot-v1.txt"),
            str(FIXTURES / "snapshot-v2.txt"),
            "--json",
        )
        body = json.loads(result.stdout)
        self.assertFalse(body["identical"])
        self.assertGreater(len(body["records"]), 0)
        self.assertIn("summary", body)

    def test_missing_file_exits_two(self) -> None:
        result = self._run(str(FIXTURES / "snapshot-v1.txt"), str(FIXTURES / "nope.txt"))
        self.assertEqual(result.returncode, 2)

    def test_directory_argument_does_not_traceback(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(str(FIXTURES / "snapshot-v1.txt"), tmp)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)

    def test_utf8_bom_is_decoded(self) -> None:
        # A file that starts with a UTF-8 BOM must decode as ordinary
        # UTF-8, not as a line whose first character is U+FEFF.
        # We compare two different files so a decoder that keeps the
        # BOM produces a different context-line first character and
        # the assertion fails. Context is widened so the first line
        # is part of the output.
        import tempfile, os
        with tempfile.NamedTemporaryFile("wb", delete=False, suffix=".txt") as f:
            f.write(b"\xef\xbb\xbfhello\nworld\n")
            b = f.name
        with tempfile.NamedTemporaryFile("wb", delete=False, suffix=".txt") as f:
            f.write(b"\xef\xbb\xbfhello\nworld!\n")
            a = f.name
        try:
            result = self._run(b, a, "--json", "--context", "5")
            self.assertEqual(result.returncode, 1)
            body = json.loads(result.stdout)
            all_lines = [r["line"] for r in body["records"]]
            self.assertIn("hello", all_lines)
            self.assertNotIn("\ufeffhello", all_lines)
        finally:
            os.unlink(b); os.unlink(a)

    def test_utf16_bom_is_decoded(self) -> None:
        # UTF-16 files (what PowerShell 5.1's `>` redirection produces) are
        # decoded by the BOM detector so the diff still runs.
        import tempfile, os
        with tempfile.NamedTemporaryFile("wb", delete=False, suffix=".txt") as f:
            f.write(b"\xff\xfe" + "alpha\nbeta\n".encode("utf-16-le"))
            b = f.name
        with tempfile.NamedTemporaryFile("wb", delete=False, suffix=".txt") as f:
            f.write(b"\xff\xfe" + "alpha\nbeta!\n".encode("utf-16-le"))
            a = f.name
        try:
            result = self._run(b, a, "--json", "--context", "5")
            self.assertEqual(result.returncode, 1)
            body = json.loads(result.stdout)
            all_lines = [r["line"] for r in body["records"]]
            self.assertIn("alpha", all_lines)
            self.assertNotIn("\ufeffalpha", all_lines)
        finally:
            os.unlink(b); os.unlink(a)

    def test_unknown_option_is_rejected(self) -> None:
        # --label-mode and --contract were removed earlier; argparse
        # must reject them so a stale command from older docs does not
        # silently do nothing useful.
        result = self._run(
            str(FIXTURES / "snapshot-v1.txt"),
            str(FIXTURES / "snapshot-v2.txt"),
            "--label-mode",
            "text",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments", result.stderr)

    def test_negative_context_is_rejected(self) -> None:
        result = self._run(
            str(FIXTURES / "snapshot-v1.txt"),
            str(FIXTURES / "snapshot-v2.txt"),
            "--context",
            "-1",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--context", result.stderr)

    def test_context_zero_trims_far_context(self) -> None:
        # 10 lines, change on line 8, --context 0 must not print lines 1..7.
        import tempfile, os
        before = "\n".join(f"line {i}" for i in range(1, 11)) + "\n"
        after  = "\n".join(f"line {i}" for i in range(1, 8)) + "\nline 8 changed\nline 9\nline 10\n"
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as f:
            f.write(before); b = f.name
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as f:
            f.write(after); a = f.name
        try:
            result = self._run(b, a, "--context", "0")
            self.assertEqual(result.returncode, 1)
            self.assertNotIn("line 1", result.stdout)
            self.assertNotIn("line 2", result.stdout)
            self.assertIn("line 8", result.stdout)
        finally:
            os.unlink(b); os.unlink(a)

    def test_demo_help_signals_in_json_output(self) -> None:
        # End-to-end: assert on the structured JSON summary, not on
        # ad-hoc text matching in the human-readable form. Asserting
        # on the text alone satisfied the round-2 tests even when the
        # structured fields were empty.
        result = self._run(
            str(HERE.parent / "examples/demo-cli/snapshots/1.0.0/list-help.txt"),
            str(HERE.parent / "examples/demo-cli/snapshots/1.1.0/list-help.txt"),
            "--json",
        )
        self.assertEqual(result.returncode, 1)
        body = json.loads(result.stdout)
        summary = body["summary"]
        self.assertEqual(summary["flags_added"], ["--filter"])
        self.assertEqual(summary["flags_removed"], ["--no-color"])
        self.assertIn("exit-code:2", summary["exit_codes_added"])

    def test_demo_json_signals_in_json_output(self) -> None:
        result = self._run(
            str(HERE.parent / "examples/demo-cli/snapshots/1.0.0/list-json.txt"),
            str(HERE.parent / "examples/demo-cli/snapshots/1.1.0/list-json.txt"),
            "--json",
        )
        self.assertEqual(result.returncode, 1)
        body = json.loads(result.stdout)
        paths = [c["path"] for c in body["summary"]["json_changes"]]
        self.assertEqual(
            sorted(p for p in paths if "tags" in p),
            ["/items[0].tags", "/items[1].tags"],
        )

    def test_demo_help_summary_signals_in_plain_text(self) -> None:
        # The plain-text output must also surface the signals, since
        # the slash command runs without --json by default.
        result = self._run(
            str(HERE.parent / "examples/demo-cli/snapshots/1.0.0/list-help.txt"),
            str(HERE.parent / "examples/demo-cli/snapshots/1.1.0/list-help.txt"),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("flags added:    ['--filter']", result.stdout)
        self.assertIn("flags removed:  ['--no-color']", result.stdout)
        self.assertIn("exit-code:2", result.stdout)


if __name__ == "__main__":
    unittest.main()
