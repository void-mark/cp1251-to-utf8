#!/usr/bin/env python3
"""Safely convert Git-tracked Oracle source files from Windows-1251 to UTF-8."""

from __future__ import annotations

import argparse
import fnmatch
import os
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


DEFAULT_INCLUDE_PATTERNS = (
    "*.sql",
    "*.ddl",
    "*.dml",
    "*.pks",
    "*.pkb",
    "*.pls",
    "*.plsql",
    "*.prc",
    "*.fnc",
    "*.trg",
    "*.vw",
    "*.tps",
    "*.tpb",
    "*.tab",
    "*.con",
    "*.idx",
    "*.seq",
    "*.syn",
    "*.grt",
    "*.ctl",
    "*.spc",
    "*.bdy",
    "*.pkg",
    "*.txt",
)


class ConfigurationError(RuntimeError):
    """Raised when the command cannot safely inspect the requested repository."""


@dataclass
class Statistics:
    discovered: int = 0
    selected: int = 0
    candidates: int = 0
    converted: int = 0
    already_utf8: int = 0
    binary: int = 0
    special: int = 0
    missing: int = 0
    errors: int = 0


def configure_console_output() -> None:
    """Avoid crashes on paths not representable by an older console code page."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="backslashreplace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Конвертирует отслеживаемые Git текстовые файлы из Windows-1251 "
            "в UTF-8 без BOM. По умолчанию выполняется только предварительный просмотр."
        )
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="корень Git-репозитория (по умолчанию: текущий каталог)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--apply",
        action="store_true",
        help="атомарно записать преобразованные файлы",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="ничего не менять; вернуть код 1, если найдены файлы Windows-1251",
    )
    parser.add_argument(
        "--include",
        action="append",
        metavar="GLOB",
        help=(
            "обрабатывать только пути по шаблону; повторяется для нескольких шаблонов. "
            "При наличии заменяет встроенный список расширений"
        ),
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help="исключить пути по шаблону; можно указать несколько раз",
    )
    parser.add_argument(
        "--all-text",
        action="store_true",
        help="проверять все отслеживаемые файлы, а не только известные расширения",
    )
    parser.add_argument(
        "--include-untracked",
        action="store_true",
        help="дополнительно проверить неотслеживаемые файлы, не исключенные Git",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="показывать также пропущенные и уже UTF-8 файлы",
    )
    return parser


def run_git(root: Path, *arguments: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", os.fspath(root), *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ConfigurationError("Git не найден в PATH") from exc

    if result.returncode != 0:
        details = result.stderr.decode("utf-8", errors="replace").strip()
        raise ConfigurationError(details or "команда Git завершилась с ошибкой")
    return result.stdout


def find_repository_root(requested_root: Path) -> Path:
    root = requested_root.expanduser().resolve()
    if not root.is_dir():
        raise ConfigurationError(f"каталог не существует: {root}")

    output = run_git(root, "rev-parse", "--show-toplevel")
    repository_root = Path(os.fsdecode(output.rstrip(b"\r\n"))).resolve()
    if repository_root != root:
        raise ConfigurationError(
            "укажите именно корень репозитория: "
            f"для {root} это {repository_root}"
        )
    return root


def list_git_files(root: Path, include_untracked: bool) -> list[Path]:
    arguments = ["ls-files", "-z", "--cached"]
    if include_untracked:
        arguments.extend(("--others", "--exclude-standard"))
    output = run_git(root, *arguments)
    relative_paths = [Path(os.fsdecode(item)) for item in output.split(b"\0") if item]
    return sorted(relative_paths, key=lambda path: os.fspath(path).casefold())


def glob_matches(relative_path: Path, pattern: str) -> bool:
    normalized_path = relative_path.as_posix().casefold()
    normalized_pattern = pattern.replace("\\", "/").casefold()
    return fnmatch.fnmatchcase(normalized_path, normalized_pattern)


def is_selected(
    relative_path: Path,
    include_patterns: Sequence[str],
    exclude_patterns: Sequence[str],
    all_text: bool,
) -> bool:
    if any(glob_matches(relative_path, pattern) for pattern in exclude_patterns):
        return False
    return all_text or any(
        glob_matches(relative_path, pattern) for pattern in include_patterns
    )


def looks_binary(data: bytes) -> bool:
    """Use a conservative binary check before attempting the single-byte codec."""
    if not data:
        return False
    if b"\x00" in data:
        return True

    sample = data[:8192]
    suspicious_controls = sum(
        byte < 32 and byte not in (9, 10, 12, 13) for byte in sample
    )
    suspicious_controls += sample.count(127)
    return suspicious_controls / len(sample) > 0.05


def classify(data: bytes) -> tuple[str, bytes | None]:
    if looks_binary(data):
        return "binary", None

    try:
        data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        pass
    else:
        return "utf8", None

    try:
        text = data.decode("cp1251", errors="strict")
    except UnicodeDecodeError:
        return "error", None

    converted = text.encode("utf-8", errors="strict")
    return "cp1251", converted


def atomic_write(path: Path, data: bytes, original_mode: int) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".utf8.tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_path, stat.S_IMODE(original_mode))
        os.replace(temporary_path, path)
    except BaseException:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        raise


def process_file(
    root: Path,
    relative_path: Path,
    apply: bool,
    verbose: bool,
    statistics: Statistics,
) -> None:
    path = root / relative_path
    display_path = relative_path.as_posix()

    try:
        metadata = path.lstat()
    except FileNotFoundError:
        statistics.missing += 1
        if verbose:
            print(f"[ПРОПУСК: НЕТ ФАЙЛА] {display_path}")
        return
    except OSError as exc:
        statistics.errors += 1
        print(f"[ОШИБКА] {display_path}: {exc}", file=sys.stderr)
        return

    if not stat.S_ISREG(metadata.st_mode):
        statistics.special += 1
        if verbose:
            print(f"[ПРОПУСК: НЕ ОБЫЧНЫЙ ФАЙЛ] {display_path}")
        return

    try:
        original = path.read_bytes()
    except OSError as exc:
        statistics.errors += 1
        print(f"[ОШИБКА ЧТЕНИЯ] {display_path}: {exc}", file=sys.stderr)
        return

    kind, converted = classify(original)
    if kind == "binary":
        statistics.binary += 1
        if verbose:
            print(f"[ПРОПУСК: БИНАРНЫЙ] {display_path}")
        return
    if kind == "utf8":
        statistics.already_utf8 += 1
        if verbose:
            print(f"[УЖЕ UTF-8] {display_path}")
        return
    if kind == "error" or converted is None:
        statistics.errors += 1
        print(
            f"[ОШИБКА КОДИРОВКИ] {display_path}: файл не является строгим "
            "UTF-8 или Windows-1251",
            file=sys.stderr,
        )
        return

    statistics.candidates += 1
    if not apply:
        print(
            f"[БУДЕТ ИЗМЕНЕН] {display_path} "
            f"({len(original)} -> {len(converted)} байт)"
        )
        return

    try:
        atomic_write(path, converted, metadata.st_mode)
    except OSError as exc:
        statistics.errors += 1
        print(f"[ОШИБКА ЗАПИСИ] {display_path}: {exc}", file=sys.stderr)
        return

    statistics.converted += 1
    print(
        f"[ПРЕОБРАЗОВАН] {display_path} "
        f"({len(original)} -> {len(converted)} байт)"
    )


def print_summary(statistics: Statistics, apply: bool) -> None:
    print()
    print("Итог:")
    print(f"  найдено Git-файлов:       {statistics.discovered}")
    print(f"  выбрано по фильтрам:      {statistics.selected}")
    print(f"  уже UTF-8/ASCII:          {statistics.already_utf8}")
    print(f"  найдено Windows-1251:     {statistics.candidates}")
    if apply:
        print(f"  преобразовано:            {statistics.converted}")
    print(f"  пропущено бинарных:       {statistics.binary}")
    print(f"  пропущено прочих/нет:     {statistics.special + statistics.missing}")
    print(f"  ошибок:                   {statistics.errors}")


def main(argv: Sequence[str] | None = None) -> int:
    configure_console_output()
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.all_text and arguments.include:
        parser.error("--all-text нельзя использовать вместе с --include")

    include_patterns = tuple(arguments.include or DEFAULT_INCLUDE_PATTERNS)
    statistics = Statistics()

    try:
        root = find_repository_root(Path(arguments.root))
        files = list_git_files(root, arguments.include_untracked)
    except ConfigurationError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2

    statistics.discovered = len(files)
    selected_files = [
        relative_path
        for relative_path in files
        if is_selected(
            relative_path,
            include_patterns,
            arguments.exclude,
            arguments.all_text,
        )
    ]
    statistics.selected = len(selected_files)

    if not arguments.apply:
        print("Режим предварительного просмотра: файлы не изменяются.")
    for relative_path in selected_files:
        process_file(
            root,
            relative_path,
            apply=arguments.apply,
            verbose=arguments.verbose,
            statistics=statistics,
        )

    print_summary(statistics, arguments.apply)

    if statistics.errors:
        return 2
    if arguments.check and statistics.candidates:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
