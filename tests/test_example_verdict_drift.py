"""Guard the demo EXAMPLE-VERDICT.md against drift.

The review-3 round found that EXAMPLE-VERDICT.md claimed its evidence
blocks were "the real output ... not a shortened transcript" but was
actually a stale copy (line numbers off by one, hand-trimmed JSON,
false sentence). This test extracts the fenced classifier-output
block from the file (the one immediately following the line "Real
output of `classify_snapshot_diff.py ... --help`") and asserts it
matches what the classifier actually prints right now, so a re-run
cannot drift again silently.
"""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
DEMO = PROJECT / "examples" / "demo-cli"
EXAMPLE_VERDICT = DEMO / "EXAMPLE-VERDICT.md"
CLASSIFY = PROJECT / "scripts" / "classify_snapshot_diff.py"


def _fenced_block_after(text: str, anchor: str) -> str | None:
    """Return the body of the first fenced ``` block that follows
    `anchor` on a later line."""
    anchor_idx = text.find(anchor)
    if anchor_idx == -1:
        return None
    pattern = re.compile(r"^```\n(.*?)^```", re.MULTILINE | re.DOTALL)
    match = pattern.search(text, pos=anchor_idx)
    return match.group(1) if match else None


def _strip_trailing_ws(text: str) -> list[str]:
    return [line.rstrip() for line in text.splitlines()]


class TestExampleVerdictDrift(unittest.TestCase):
    def setUp(self) -> None:
        self.text = EXAMPLE_VERDICT.read_text(encoding="utf-8")

    def _run_classifier(self) -> str:
        result = subprocess.run(
            [
                sys.executable, str(CLASSIFY),
                str(DEMO / "snapshots" / "1.0.0" / "list-help.txt"),
                str(DEMO / "snapshots" / "1.1.0" / "list-help.txt"),
            ],
            capture_output=True, text=True, cwd=str(PROJECT),
        )
        self.assertEqual(
            result.returncode, 1,
            msg=f"unexpected return code {result.returncode}: {result.stderr}",
        )
        return result.stdout

    def test_classifier_output_block_matches_real_run(self) -> None:
        anchor = "snapshots/1.0.0/list-help.txt\nsnapshots/1.1.0/list-help.txt"
        block = _fenced_block_after(self.text, anchor)
        self.assertIsNotNone(block, "no fenced block after the help-diff anchor")
        expected = self._run_classifier()
        # Compare line by line after stripping trailing whitespace.
        # The classifier's f-string formatter leaves a trailing space
        # on lines that came from a stripped newline; the EXAMPLE-
        # VERDICT drops it. The substantive content is what matters.
        self.assertEqual(
            _strip_trailing_ws(block),
            _strip_trailing_ws(expected),
        )

    def test_classifier_output_block_contains_signals_header(self) -> None:
        # The classifier output ends with the literal string
        # '--- signals (these are evidence, not a verdict)'; the
        # EXAMPLE-VERDICT must carry the same wording.
        anchor = "snapshots/1.0.0/list-help.txt\nsnapshots/1.1.0/list-help.txt"
        block = _fenced_block_after(self.text, anchor)
        self.assertIsNotNone(block)
        self.assertIn("--- signals (these are evidence, not a verdict)", block)

    def test_changelog_default_change_under_breaking_unless_confirmed(self) -> None:
        # Round 3 had the --limit default change listed under
        # ### Compatible while the per-change summary called it
        # breaking unless confirmed. The CHANGELOG must match the
        # per-change summary; the maintainer decides which heading
        # is right but they cannot disagree.
        anchor = "## CHANGELOG entry"
        tail = self.text[self.text.find(anchor):]
        # Find the "## What the maintainer should do" section that
        # ends the CHANGELOG; the --limit bullet must appear above
        # it.
        end = tail.find("## What the maintainer should do")
        section = tail[:end] if end != -1 else tail
        self.assertIn("--limit", section)
        # Locate the heading under which --limit appears.
        for heading in section.split("### ")[1:]:
            if "--limit" in heading:
                # The section may be either "Breaking" or "Breaking
                # unless confirmed" (or any wording the maintainer
                # uses for that semantic). It must NOT be "Compatible".
                self.assertNotIn("### Compatible", "### " + heading)
                break


if __name__ == "__main__":
    unittest.main()
