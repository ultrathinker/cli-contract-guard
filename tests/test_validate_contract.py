"""Tests for validate_contract.py.

These tests are runnable without third-party packages. Run them via
    python tests/run_tests.py
or
    python -m unittest tests.test_validate_contract
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "validate_contract.py"
FIXTURES = HERE / "fixtures"
sys.path.insert(0, str(HERE.parent / "scripts"))
import validate_contract  # noqa: E402  (after sys.path tweak)


class TestImport(unittest.TestCase):
    def test_module_imports(self) -> None:
        self.assertTrue(hasattr(validate_contract, "validate"))
        self.assertTrue(hasattr(validate_contract, "main"))


class TestSchemaConstants(unittest.TestCase):
    def test_schema_version(self) -> None:
        self.assertEqual(validate_contract.SCHEMA_VERSION, "1")

    def test_stability_values(self) -> None:
        self.assertEqual(
            validate_contract.STABILITY_VALUES,
            {"experimental", "beta", "stable", "locked", "deprecated"},
        )

    def test_policy_values(self) -> None:
        self.assertEqual(
            validate_contract.POLICY_VALUES,
            {"minor", "patch-only", "locked", "experimental"},
        )

    def test_audience_values(self) -> None:
        self.assertEqual(validate_contract.AUDIENCE_VALUES, {"humans", "scripts"})


class TestValidContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with open(FIXTURES / "valid-contract.json", "r", encoding="utf-8") as f:
            cls.data = json.load(f)

    def test_validate_walks_without_errors(self) -> None:
        issues: list[validate_contract.Issue] = []
        validate_contract.validate(self.data, issues)
        errors = [i for i in issues if i.severity == "error"]
        self.assertEqual(errors, [], f"unexpected errors: {[e.to_dict() for e in errors]}")

    def test_validate_emits_no_warnings(self) -> None:
        issues: list[validate_contract.Issue] = []
        validate_contract.validate(self.data, issues)
        warnings = [i for i in issues if i.severity == "warning"]
        self.assertEqual(warnings, [], f"unexpected warnings: {[w.to_dict() for w in warnings]}")


class TestInvalidContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with open(FIXTURES / "invalid-contract.json", "r", encoding="utf-8") as f:
            cls.data = json.load(f)

    def _collect_errors(self) -> list[validate_contract.Issue]:
        issues: list[validate_contract.Issue] = []
        validate_contract.validate(self.data, issues)
        return [i for i in issues if i.severity == "error"]

    def _collect_warnings(self) -> list[validate_contract.Issue]:
        issues: list[validate_contract.Issue] = []
        validate_contract.validate(self.data, issues)
        return [i for i in issues if i.severity == "warning"]

    def test_rejects_unsupported_schema_version(self) -> None:
        errors = self._collect_errors()
        self.assertTrue(any("schema_version" in e.path and "99" in e.message for e in errors))

    def test_rejects_tool_name_with_uppercase_or_spaces(self) -> None:
        # Tool names must match TOOL_NAME; the invalid fixture uses
        # "Demo Spaces" which fails on both counts (uppercase and space).
        errors = self._collect_errors()
        self.assertTrue(any(e.path == "$.tool.name" for e in errors))

    def test_rejects_unknown_policy(self) -> None:
        errors = self._collect_errors()
        self.assertTrue(any(e.path == "$.stability.policy" for e in errors))

    def test_rejects_unknown_audience(self) -> None:
        errors = self._collect_errors()
        self.assertTrue(any(e.path == "$.stability.audiences" for e in errors))

    def test_rejects_empty_meaning_and_duplicate_exit_codes(self) -> None:
        errors = self._collect_errors()
        self.assertTrue(any("meaning" in e.path and "non-empty" in e.message for e in errors))
        self.assertTrue(any("duplicate exit code" in e.message for e in errors))

    def test_rejects_global_flag_without_dashes(self) -> None:
        errors = self._collect_errors()
        self.assertTrue(any(e.path == "$.global_flags[0].name" for e in errors))

    def test_rejects_invalid_flag_type(self) -> None:
        errors = self._collect_errors()
        self.assertTrue(any(e.path == "$.global_flags[0].type" for e in errors))

    def test_rejects_invalid_since_versions(self) -> None:
        errors = self._collect_errors()
        self.assertTrue(any(e.path == "$.global_flags[0].since" for e in errors))
        self.assertTrue(any(e.path == "$.commands[0].since" for e in errors))

    def test_rejects_unknown_command_stability(self) -> None:
        errors = self._collect_errors()
        self.assertTrue(any(e.path == "$.commands[0].stability" for e in errors))

    def test_allows_uppercase_command_name(self) -> None:
        # Real CLIs name things `getUser`, `Deploy`, `MSBuild`. The
        # validator accepts those; what it rejects is whitespace in a
        # tool name (see fixture `Demo Spaces`).
        errors = self._collect_errors()
        self.assertFalse(any(e.path == "$.commands[0].name" for e in errors))

    def test_rejects_tool_name_with_spaces(self) -> None:
        errors = self._collect_errors()
        self.assertTrue(any(e.path == "$.tool.name" for e in errors))

    def test_rejects_argument_required_not_bool(self) -> None:
        errors = self._collect_errors()
        self.assertTrue(any(e.path == "$.commands[0].arguments[0].required" for e in errors))

    def test_rejects_numeric_command_summary(self) -> None:
        errors = self._collect_errors()
        self.assertTrue(any(e.path == "$.commands[0].summary" for e in errors))

    def test_rejects_unknown_stdout_format(self) -> None:
        errors = self._collect_errors()
        self.assertTrue(any(e.path == "$.commands[0].stdout_format" for e in errors))

    def test_rejects_duplicate_command_flag(self) -> None:
        errors = self._collect_errors()
        self.assertTrue(any(e.path == "$.commands[0].flags[1].name" for e in errors))

    def test_rejects_duplicate_global_flag(self) -> None:
        errors = self._collect_errors()
        self.assertTrue(any(e.path == "$.global_flags[1].name" for e in errors))

    def test_rejects_invalid_json_output_stable_since(self) -> None:
        errors = self._collect_errors()
        self.assertTrue(any(e.path == "$.commands[0].json_output.stable_since" for e in errors))

    def test_rejects_non_object_command_entry(self) -> None:
        errors = self._collect_errors()
        self.assertTrue(any(e.path == "$.commands[1]" for e in errors))

    def test_warns_on_undefined_exit_code(self) -> None:
        warnings = self._collect_warnings()
        self.assertTrue(any(e.path == "$.commands[0].exit_codes" for e in warnings))


class TestUnknownKeys(unittest.TestCase):
    def _validate(self, payload: dict) -> tuple[list[validate_contract.Issue], list[validate_contract.Issue]]:
        issues: list[validate_contract.Issue] = []
        validate_contract.validate(payload, issues)
        errors = [i for i in issues if i.severity == "error"]
        warnings = [i for i in issues if i.severity == "warning"]
        return errors, warnings

    def _minimal_contract(self, **overrides: Any) -> dict:
        base = {
            "schema_version": "1",
            "tool": {"name": "demo"},
            "stability": {"policy": "minor", "audiences": ["humans"]},
            "commands": [],
        }
        base.update(overrides)
        return base

    def test_typo_at_top_level_warns(self) -> None:
        contract = self._minimal_contract(exit_code=[])
        _, warnings = self._validate(contract)
        self.assertTrue(any("exit_code" in w.path and "unknown key" in w.message for w in warnings))

    def test_typo_inside_tool_warns(self) -> None:
        contract = self._minimal_contract()
        contract["tool"]["disply_name"] = "X"
        _, warnings = self._validate(contract)
        self.assertTrue(any(w.path == "$.tool.disply_name" for w in warnings))

    def test_typo_inside_command_warns(self) -> None:
        contract = self._minimal_contract(commands=[{"name": "list", "summary": "List"}])
        contract["commands"][0]["flgs"] = []
        _, warnings = self._validate(contract)
        self.assertTrue(any(w.path == "$.commands[0].flgs" for w in warnings))

    def test_typo_inside_exit_codes_warns(self) -> None:
        contract = self._minimal_contract(exit_codes=[{"code": 0, "meaning": "ok", "since": "1.0.0"}])
        _, warnings = self._validate(contract)
        self.assertTrue(any("exit_codes[0].since" in w.path for w in warnings))

    def test_x_prefix_passes_silently(self) -> None:
        contract = self._minimal_contract()
        contract["tool"]["x-internal-id"] = "abc"
        _, warnings = self._validate(contract)
        self.assertFalse(any(w.path == "$.tool.x-internal-id" for w in warnings))


class TestExitCodeRange(unittest.TestCase):
    def _minimal(self, **overrides: Any) -> dict:
        base = {
            "schema_version": "1",
            "tool": {"name": "demo"},
            "stability": {"policy": "minor", "audiences": ["humans"]},
            "commands": [
                {"name": "list", "summary": "List", "exit_codes": [0, 1]},
            ],
            "exit_codes": [
                {"code": 0, "meaning": "ok"},
                {"code": 1, "meaning": "err"},
            ],
        }
        base.update(overrides)
        return base

    def _errors(self, contract: dict) -> list[validate_contract.Issue]:
        issues: list[validate_contract.Issue] = []
        validate_contract.validate(contract, issues)
        return [i for i in issues if i.severity == "error"]

    def test_out_of_range_command_exit_code_is_error(self) -> None:
        contract = self._minimal()
        contract["commands"][0]["exit_codes"] = [0, 999, -1]
        errors = self._errors(contract)
        self.assertTrue(any("must be in 0..255" in e.message for e in errors))


class TestOptionalFieldTypes(unittest.TestCase):
    def _minimal(self, **overrides: Any) -> dict:
        base = {
            "schema_version": "1",
            "tool": {"name": "demo"},
            "stability": {"policy": "minor", "audiences": ["humans"]},
            "commands": [],
        }
        base.update(overrides)
        return base

    def _errors(self, contract: dict) -> list[validate_contract.Issue]:
        issues: list[validate_contract.Issue] = []
        validate_contract.validate(contract, issues)
        return [i for i in issues if i.severity == "error"]

    def test_homepage_must_be_string(self) -> None:
        contract = self._minimal()
        contract["tool"]["homepage"] = 42
        errors = self._errors(contract)
        self.assertTrue(any(e.path == "$.tool.homepage" for e in errors))

    def test_tool_description_must_be_string(self) -> None:
        contract = self._minimal()
        contract["tool"]["description"] = ["not a string"]
        errors = self._errors(contract)
        self.assertTrue(any(e.path == "$.tool.description" for e in errors))

    def test_environment_respects_must_be_string_list(self) -> None:
        contract = self._minimal(environment={"respects": "NO_COLOR"})
        errors = self._errors(contract)
        self.assertTrue(any(e.path == "$.environment.respects" for e in errors))

    def test_environment_tty_aware_must_be_bool(self) -> None:
        contract = self._minimal(environment={"tty_aware": "yes"})
        errors = self._errors(contract)
        self.assertTrue(any(e.path == "$.environment.tty_aware" for e in errors))

    def test_command_notes_must_be_string(self) -> None:
        contract = self._minimal(commands=[{"name": "list", "summary": "List", "notes": 42}])
        errors = self._errors(contract)
        self.assertTrue(any(e.path == "$.commands[0].notes" for e in errors))

    def test_flag_required_must_be_bool(self) -> None:
        contract = self._minimal(commands=[{
            "name": "list", "summary": "List",
            "flags": [{"name": "--foo", "type": "string", "required": "yes"}],
        }])
        errors = self._errors(contract)
        self.assertTrue(any(e.path == "$.commands[0].flags[0].required" for e in errors))

    def test_flag_default_wrong_type_for_int_flag(self) -> None:
        contract = self._minimal(commands=[{
            "name": "list", "summary": "List",
            "flags": [{"name": "--count", "type": "int", "default": "5"}],
        }])
        errors = self._errors(contract)
        self.assertTrue(any(e.path == "$.commands[0].flags[0].default" for e in errors))

    def test_flag_choices_must_be_string_list(self) -> None:
        contract = self._minimal(commands=[{
            "name": "list", "summary": "List",
            "flags": [{"name": "--fmt", "type": "enum", "choices": [1, 2, 3]}],
        }])
        errors = self._errors(contract)
        self.assertTrue(any(e.path == "$.commands[0].flags[0].choices" for e in errors))


class TestArguments(unittest.TestCase):
    def _errors(self, contract: dict) -> list[validate_contract.Issue]:
        issues: list[validate_contract.Issue] = []
        validate_contract.validate(contract, issues)
        return [i for i in issues if i.severity == "error"]

    def _minimal_cmd(self, **kwargs: Any) -> dict:
        base = {
            "schema_version": "1",
            "tool": {"name": "demo"},
            "stability": {"policy": "minor", "audiences": ["humans"]},
            "commands": [{"name": "cp", "summary": "Copy", **kwargs}],
        }
        return base

    def test_duplicate_argument_names(self) -> None:
        contract = self._minimal_cmd(arguments=[
            {"name": "PATH"},
            {"name": "PATH"},
        ])
        errors = self._errors(contract)
        self.assertTrue(any("duplicate argument name" in e.message for e in errors))

    def test_only_last_argument_may_be_variadic(self) -> None:
        contract = self._minimal_cmd(arguments=[
            {"name": "FIRST", "variadic": True},
            {"name": "LAST"},
        ])
        errors = self._errors(contract)
        self.assertTrue(any("only the last argument may be variadic" in e.message for e in errors))

    def test_last_argument_variadic_is_ok(self) -> None:
        contract = self._minimal_cmd(arguments=[
            {"name": "FIRST"},
            {"name": "REST", "variadic": True},
        ])
        errors = self._errors(contract)
        self.assertFalse(any("variadic" in e.message for e in errors))


class TestJsonOutputKeyCheck(unittest.TestCase):
    def _minimal(self, **overrides: Any) -> dict:
        base = {
            "schema_version": "1",
            "tool": {"name": "demo"},
            "stability": {"policy": "minor", "audiences": ["humans"]},
            "commands": [{"name": "list", "summary": "List", "json_output": overrides}],
        }
        return base

    def _warnings(self, contract: dict) -> list[validate_contract.Issue]:
        issues: list[validate_contract.Issue] = []
        validate_contract.validate(contract, issues)
        return [i for i in issues if i.severity == "warning"]

    def test_unknown_key_in_json_output_warns(self) -> None:
        contract = self._minimal(stable_since="1.0.0", schema="schemas/list.schema.json", schemma="x")
        warnings = self._warnings(contract)
        self.assertTrue(any("json_output.schemma" in w.path for w in warnings))

    def test_json_output_notes_must_be_string(self) -> None:
        contract = self._minimal(notes=42)
        issues: list[validate_contract.Issue] = []
        validate_contract.validate(contract, issues)
        errors = [i for i in issues if i.severity == "error"]
        self.assertTrue(any("json_output.notes" in e.path for e in errors))


class TestValidatorEncodingSafety(unittest.TestCase):
    """The validator must not traceback when a non-ASCII value is echoed
    back to a cp1252 console. Regression for the round-2 partial fix."""

    def test_cp1252_stdout_does_not_traceback(self) -> None:
        import os
        import subprocess
        import tempfile

        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(
                {
                    "schema_version": "1",
                    "tool": {"name": "x"},
                    "stability": {"policy": "minor→", "audiences": ["humans"]},
                    "commands": [],
                },
                f,
                ensure_ascii=False,
            )
            path = f.name
        try:
            env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
            result = subprocess.run(
                [sys.executable, str(SCRIPT), path],
                capture_output=True, text=True, env=env,
                cwd=str(HERE.parent),
            )
            self.assertNotIn("Traceback", result.stderr)
            self.assertNotEqual(result.returncode, 0)
        finally:
            os.unlink(path)


class TestRejectsTopLevelScalars(unittest.TestCase):
    def test_top_level_array_rejected(self) -> None:
        issues: list[validate_contract.Issue] = []
        validate_contract.validate([], issues)
        self.assertTrue(any(i.path == "$" for i in issues))

    def test_top_level_null_rejected(self) -> None:
        issues: list[validate_contract.Issue] = []
        validate_contract.validate(None, issues)
        self.assertTrue(any(i.path == "$" for i in issues))


class TestSchemaFlexibility(unittest.TestCase):
    def _errors(self, contract: dict) -> list[validate_contract.Issue]:
        issues: list[validate_contract.Issue] = []
        validate_contract.validate(contract, issues)
        return [i for i in issues if i.severity == "error"]

    def _minimal(self, **overrides: Any) -> dict:
        base = {
            "schema_version": "1",
            "tool": {"name": "demo"},
            "stability": {"policy": "minor", "audiences": ["humans"]},
            "commands": [],
        }
        base.update(overrides)
        return base

    def test_tool_name_msbuild(self) -> None:
        contract = self._minimal(tool={"name": "MSBuild"})
        self.assertEqual(self._errors(contract), [])

    def test_command_path_with_space(self) -> None:
        contract = self._minimal(commands=[{"name": "remote add", "summary": "Add a remote"}])
        self.assertEqual(self._errors(contract), [])

    def test_command_path_with_colon(self) -> None:
        contract = self._minimal(commands=[{"name": "plugins:install", "summary": "Install plugin"}])
        self.assertEqual(self._errors(contract), [])

    def test_command_name_with_camelcase(self) -> None:
        contract = self._minimal(commands=[{"name": "getUser", "summary": "Get a user"}])
        self.assertEqual(self._errors(contract), [])

    def test_command_name_with_digits(self) -> None:
        contract = self._minimal(commands=[{"name": "v2 migrate", "summary": "Migrate v2"}])
        self.assertEqual(self._errors(contract), [])

    def test_flag_with_underscore(self) -> None:
        contract = self._minimal(commands=[{
            "name": "build", "summary": "Build",
            "flags": [{"name": "--dry_run", "type": "bool"}],
        }])
        self.assertEqual(self._errors(contract), [])

    def test_positional_arguments(self) -> None:
        contract = self._minimal(commands=[{
            "name": "cp", "summary": "Copy",
            "arguments": [
                {"name": "SRC", "required": True},
                {"name": "DST", "required": True},
                {"name": "EXTRA", "variadic": True},
            ],
        }])
        self.assertEqual(self._errors(contract), [])

    def test_arguments_field_rejects_unknown_keys(self) -> None:
        contract = self._minimal(commands=[{
            "name": "cp", "summary": "Copy",
            "arguments": [{"name": "PATH", "default": "x"}],
        }])
        issues: list[validate_contract.Issue] = []
        validate_contract.validate(contract, issues)
        warnings = [i for i in issues if i.severity == "warning"]
        self.assertTrue(any(e.path == "$.commands[0].arguments[0].default" for e in warnings))


class TestCliInvocation(unittest.TestCase):
    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            cwd=str(HERE.parent),
        )

    def test_valid_contract_exits_zero(self) -> None:
        result = self._run(str(FIXTURES / "valid-contract.json"))
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("OK", result.stdout)

    def test_invalid_contract_exits_one(self) -> None:
        result = self._run(str(FIXTURES / "invalid-contract.json"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR", result.stdout)

    def test_invalid_json_exits_two(self) -> None:
        bad = FIXTURES / "broken-json.json"
        bad.write_text("{not valid json", encoding="utf-8")
        try:
            result = self._run(str(bad))
            self.assertEqual(result.returncode, 2)
            self.assertIn("invalid JSON", result.stderr)
        finally:
            os.remove(bad)

    def test_missing_file_exits_two(self) -> None:
        result = self._run(str(FIXTURES / "does-not-exist.json"))
        self.assertEqual(result.returncode, 2)

    def test_directory_argument_does_not_traceback(self) -> None:
        # If the user passes a directory (a common typo), the script must
        # print a one-line error, not a traceback.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(tmp)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)

    def test_bom_prefixed_json_is_accepted(self) -> None:
        bom_path = FIXTURES / "bom-contract.json"
        with open(FIXTURES / "valid-contract.json", "rb") as f:
            raw = f.read()
        bom_path.write_bytes(b"\xef\xbb\xbf" + raw)
        try:
            result = self._run(str(bom_path))
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        finally:
            bom_path.unlink(missing_ok=True)

    def test_json_output_is_parseable(self) -> None:
        result = self._run(str(FIXTURES / "invalid-contract.json"), "--json")
        body = json.loads(result.stdout)
        self.assertFalse(body["ok"])
        self.assertGreater(len(body["issues"]), 0)
        self.assertTrue(all({"severity", "path", "message"} <= set(i) for i in body["issues"]))


if __name__ == "__main__":
    unittest.main()
