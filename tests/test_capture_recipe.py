"""Tests that the snapshot-capture recipes in the contract-init
skill actually produce a structured snapshot when run against a fake
tool.

The POSIX recipe is run via bash on every platform that has it
(Git Bash on Windows, bash on macOS/Linux). The test skips when no
POSIX shell is available, rather than marking it as broken on
Windows-only runners.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent / "skills" / "contract-init" / "SKILL.md"
FIXTURES = HERE / "fixtures"


def _have_posix_shell() -> str | None:
    for name in ("bash", "sh"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _extract_first_fenced_block(text: str, marker: str) -> str | None:
    """Return the body of the first fenced block whose opening fence
    carries the given marker (`sh`, `powershell`, etc.)."""
    pattern = re.compile(r"^```" + re.escape(marker) + r"\n(.*?)^```", re.MULTILINE | re.DOTALL)
    match = pattern.search(text)
    return match.group(1) if match else None


class TestPosixCaptureRecipe(unittest.TestCase):
    """Run the POSIX recipe block extracted from the SKILL against
    the fake tool and assert the snapshot parses as structured."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.shell = _have_posix_shell()
        if cls.shell is None:
            return
        recipe = _extract_first_fenced_block(SKILL.read_text(encoding="utf-8"), "sh")
        if recipe is None:
            raise unittest.SkipTest("no `sh` block in the SKILL")
        cls.recipe = recipe

    def setUp(self) -> None:
        if self.shell is None:
            self.skipTest("no POSIX shell on PATH (bash or sh)")

    def test_recipe_produces_structured_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()
            # The recipe calls `mytool` and assumes it is on PATH.
            # Put a shim wrapper for the fake tool on a private PATH
            # so the test does not touch the user's environment.
            # The fake tool runs under the interpreter that runs this
            # test, not under a bare `python`: macOS and most Linux
            # systems only have `python3`. Both paths are quoted
            # because the Windows temp folder contains spaces.
            (bin_dir / "mytool").write_text(
                "#!/bin/sh\n"
                f'"{sys.executable}" "{FIXTURES / "fake_tool.py"}" "$@"\n',
                encoding="utf-8",
            )
            (bin_dir / "mytool").chmod(0o755)
            snapshots = tmp_path / "snapshots"
            snapshots.mkdir()
            script = tmp_path / "snap.sh"
            script.write_text(
                "#!/bin/sh\n" + self.recipe,
                encoding="utf-8",
            )
            script.chmod(0o755)
            env = {**os.environ, "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]}
            result = subprocess.run(
                [self.shell, str(script)],
                capture_output=True,
                text=True,
                cwd=str(tmp_path),
                env=env,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            snapshot = snapshots / "0.1.0" / "help.txt"
            self.assertTrue(snapshot.exists())
            text = snapshot.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("$ mytool"), f"unexpected start: {text[:40]!r}")
            self.assertIn("--- stderr", text)
            self.assertIn("--- exit 2", text)
            # Parse the snapshot through the classifier's parser.
            sys.path.insert(0, str(HERE.parent / "scripts"))
            import classify_snapshot_diff  # noqa: E402
            snap = classify_snapshot_diff.parse_snapshot(text.splitlines())
            self.assertTrue(snap["structured"])
            self.assertEqual(snap["command"], "mytool --help")
            self.assertIn("Usage: fake-tool [options]", snap["stdout"])
            self.assertEqual(snap["stderr"], [
                "WARN: deprecated flag --foo",
                "INFO: connecting",
            ])
            self.assertEqual(snap["exit_code"], 2)

    def test_printf_exit_does_not_use_double_dash_format(self) -> None:
        # Regression for the round-4 review finding: the trailing
        # printf that writes the `--- exit N` line must use end-of-
        # options or a format that does not start with `--`, otherwise
        # bash and dash both fail with "invalid option".
        self.assertIn("printf -- '--- exit %d\\n'", self.recipe)
        bad = re.search(r"printf '--- exit %d", self.recipe)
        self.assertIsNone(bad, "found the broken printf '--- exit %d form")


if __name__ == "__main__":
    unittest.main()
