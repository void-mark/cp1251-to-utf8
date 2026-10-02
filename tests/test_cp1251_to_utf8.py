from __future__ import annotations

import importlib.util
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "cp1251_to_utf8.py"
HOOK = PROJECT_ROOT / ".githooks" / "pre-commit"
POSIX_SETUP = PROJECT_ROOT / "tools" / "setup-repository.sh"
POWERSHELL_SETUP = PROJECT_ROOT / "tools" / "setup-repository.ps1"
CMD_SETUP = PROJECT_ROOT / "tools" / "setup-repository.cmd"
SPEC = importlib.util.spec_from_file_location("cp1251_to_utf8", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ClassificationTests(unittest.TestCase):
    def test_cp1251_is_converted_to_utf8(self) -> None:
        source = "-- Миграция\r\nselect 'Привет' from dual;\r\n".encode("cp1251")
        kind, converted = MODULE.classify(source)
        self.assertEqual(kind, "cp1251")
        self.assertEqual(
            converted,
            "-- Миграция\r\nselect 'Привет' from dual;\r\n".encode("utf-8"),
        )

    def test_utf8_is_not_changed(self) -> None:
        kind, converted = MODULE.classify("select 'Привет';\n".encode("utf-8"))
        self.assertEqual(kind, "utf8")
        self.assertIsNone(converted)

    def test_ascii_is_already_utf8(self) -> None:
        kind, converted = MODULE.classify(b"select sysdate from dual;\n")
        self.assertEqual(kind, "utf8")
        self.assertIsNone(converted)

    def test_binary_is_skipped(self) -> None:
        kind, converted = MODULE.classify(b"PK\x03\x04\x00binary\x00data")
        self.assertEqual(kind, "binary")
        self.assertIsNone(converted)

    def test_undefined_cp1251_byte_is_an_error(self) -> None:
        kind, converted = MODULE.classify(b"select '\x98' from dual;")
        self.assertEqual(kind, "error")
        self.assertIsNone(converted)

    def test_common_oracle_migration_extensions_are_selected(self) -> None:
        for file_name in ("001.ddl", "002.dml", "package.spc", "body.bdy"):
            with self.subTest(file_name=file_name):
                self.assertTrue(
                    MODULE.is_selected(
                        Path(file_name),
                        MODULE.DEFAULT_INCLUDE_PATTERNS,
                        (),
                        False,
                    )
                )


class IntegrationFileTests(unittest.TestCase):
    def test_posix_scripts_have_valid_shell_syntax(self) -> None:
        shell = shutil.which("sh")
        if shell is None:
            self.skipTest("POSIX shell is not available")
        for script in (HOOK, POSIX_SETUP):
            with self.subTest(script=script.name):
                result = subprocess.run(
                    [shell, "-n", os.fspath(script)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_windows_scripts_are_ascii_compatible_with_powershell_51(self) -> None:
        POWERSHELL_SETUP.read_bytes().decode("ascii")
        CMD_SETUP.read_bytes().decode("ascii")

    def test_gitattributes_protects_hook_line_endings(self) -> None:
        attributes = (PROJECT_ROOT / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("/.githooks/* text eol=lf", attributes)

    def test_hook_checks_the_staged_blob_instead_of_worktree(self) -> None:
        shell = shutil.which("sh")
        if shell is None:
            self.skipTest("POSIX shell is not available")

        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            subprocess.run(["git", "init", "-q", os.fspath(repository)], check=True)
            shutil.copy2(SCRIPT, repository / SCRIPT.name)

            legacy_path = repository / "staged.sql"
            legacy_path.write_bytes("-- Старый файл\n".encode("cp1251"))
            subprocess.run(
                ["git", "-C", os.fspath(repository), "add", "."], check=True
            )

            # Only the working tree becomes UTF-8; the index intentionally stays CP1251.
            legacy_path.write_bytes("-- Старый файл\n".encode("utf-8"))
            rejected = subprocess.run(
                [shell, os.fspath(HOOK)],
                cwd=repository,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(rejected.returncode, 1, rejected.stderr)
            self.assertIn("staged.sql", rejected.stderr)

            subprocess.run(
                ["git", "-C", os.fspath(repository), "add", "staged.sql"],
                check=True,
            )
            accepted = subprocess.run(
                [shell, os.fspath(HOOK)],
                cwd=repository,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(accepted.returncode, 0, accepted.stderr)

    def test_posix_setup_configures_repository_hook_path(self) -> None:
        shell = shutil.which("sh")
        if shell is None:
            self.skipTest("POSIX shell is not available")

        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            (repository / ".githooks").mkdir()
            (repository / "tools").mkdir()
            shutil.copy2(SCRIPT, repository / SCRIPT.name)
            shutil.copy2(HOOK, repository / ".githooks" / "pre-commit")
            shutil.copy2(POSIX_SETUP, repository / "tools" / "setup-repository.sh")

            subprocess.run(["git", "init", "-q", os.fspath(repository)], check=True)
            (repository / "valid.sql").write_text(
                "-- UTF-8: Привет\nselect 1 from dual;\n", encoding="utf-8"
            )
            subprocess.run(
                ["git", "-C", os.fspath(repository), "add", "."], check=True
            )

            result = subprocess.run(
                [shell, os.fspath(repository / "tools" / "setup-repository.sh")],
                cwd=repository,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            configured_path = subprocess.check_output(
                [
                    "git",
                    "-C",
                    os.fspath(repository),
                    "config",
                    "--local",
                    "--get",
                    "core.hooksPath",
                ],
                text=True,
            ).strip()
            self.assertEqual(configured_path, ".githooks")


class CommandLineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary_directory.name)
        subprocess.run(
            ["git", "init", "-q", os.fspath(self.repository)], check=True
        )

        self.legacy = self.repository / "packages" / "Тест package.pkb"
        self.legacy.parent.mkdir()
        self.legacy_text = (
            "create or replace package body тест as\r\n"
            "  -- Комментарий\r\n"
            "end тест;\r\n/\r\n"
        )
        self.legacy.write_bytes(self.legacy_text.encode("cp1251"))
        self.legacy.chmod(0o754)

        (self.repository / "already.sql").write_text(
            "-- Уже UTF-8\nselect 1 from dual;\n", encoding="utf-8"
        )
        (self.repository / "ignored.md").write_bytes("Старый текст".encode("cp1251"))
        (self.repository / "binary.sql").write_bytes(b"SQL\x00\x01\x02data")
        subprocess.run(
            ["git", "-C", os.fspath(self.repository), "add", "."], check=True
        )

        self.untracked = self.repository / "untracked.sql"
        self.untracked.write_bytes("-- Неотслеживаемый".encode("cp1251"))

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def run_tool(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, os.fspath(SCRIPT), *arguments, os.fspath(self.repository)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

    def test_preview_does_not_modify_files(self) -> None:
        before = self.legacy.read_bytes()
        result = self.run_tool()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[БУДЕТ ИЗМЕНЕН] packages/Тест package.pkb", result.stdout)
        self.assertEqual(self.legacy.read_bytes(), before)
        self.assertEqual(self.untracked.read_bytes(), "-- Неотслеживаемый".encode("cp1251"))

    def test_check_returns_one_when_conversion_is_needed(self) -> None:
        result = self.run_tool("--check")
        self.assertEqual(result.returncode, 1, result.stderr)

    def test_apply_converts_atomically_and_preserves_mode_and_crlf(self) -> None:
        original_mode = stat.S_IMODE(self.legacy.stat().st_mode)
        result = self.run_tool("--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.legacy.read_bytes(), self.legacy_text.encode("utf-8"))
        self.assertEqual(stat.S_IMODE(self.legacy.stat().st_mode), original_mode)
        self.assertIn(b"\r\n", self.legacy.read_bytes())
        self.assertEqual(
            self.untracked.read_bytes(), "-- Неотслеживаемый".encode("cp1251")
        )

        check_result = self.run_tool("--check")
        self.assertEqual(check_result.returncode, 0, check_result.stderr)
        self.assertIn("найдено Windows-1251:     0", check_result.stdout)

    def test_include_untracked_converts_untracked_file(self) -> None:
        result = self.run_tool("--apply", "--include-untracked")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.untracked.read_bytes(), "-- Неотслеживаемый".encode("utf-8")
        )

    def test_default_extensions_skip_markdown(self) -> None:
        result = self.run_tool("--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (self.repository / "ignored.md").read_bytes(),
            "Старый текст".encode("cp1251"),
        )

    def test_custom_include_replaces_default_extensions(self) -> None:
        result = self.run_tool("--apply", "--include", "*.md")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (self.repository / "ignored.md").read_bytes(),
            "Старый текст".encode("utf-8"),
        )
        self.assertEqual(self.legacy.read_bytes(), self.legacy_text.encode("cp1251"))


if __name__ == "__main__":
    unittest.main()
