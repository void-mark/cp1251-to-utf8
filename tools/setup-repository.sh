#!/bin/sh

# Repository bootstrap for macOS, Linux and Git Bash on Windows.

set -eu

if ! command -v git >/dev/null 2>&1; then
    echo "Setup failed: Git was not found in PATH." >&2
    exit 2
fi

if command -v python3 >/dev/null 2>&1 && \
   python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' \
   >/dev/null 2>&1; then
    run_python() { python3 "$@"; }
elif command -v py >/dev/null 2>&1 && \
     py -3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' \
     >/dev/null 2>&1; then
    run_python() { py -3 "$@"; }
elif command -v python >/dev/null 2>&1 && \
     python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' \
     >/dev/null 2>&1; then
    run_python() { python "$@"; }
else
    echo "Setup failed: Python 3.9+ was not found." >&2
    echo "Install Python and make python3, py, or python available in PATH." >&2
    exit 2
fi

script_directory=$(cd "$(dirname "$0")" && pwd)
repository_root=$(git -C "$script_directory/.." rev-parse --show-toplevel)

cd "$repository_root"

if [ ! -f ".githooks/pre-commit" ]; then
    echo "Setup failed: .githooks/pre-commit was not found." >&2
    exit 2
fi

if [ ! -f "cp1251_to_utf8.py" ]; then
    echo "Setup failed: cp1251_to_utf8.py was not found." >&2
    exit 2
fi

current_hooks_path=$(git config --get core.hooksPath || true)

if [ -n "$current_hooks_path" ] && [ "$current_hooks_path" != ".githooks" ]; then
    echo "Setup stopped: another Git hooks directory is already configured:" >&2
    echo "  core.hooksPath = $current_hooks_path" >&2
    echo "Merge the existing hooks with .githooks manually." >&2
    exit 2
fi

chmod +x ".githooks/pre-commit" "tools/setup-repository.sh" \
    "cp1251_to_utf8.py"
git config --local core.hooksPath .githooks

echo "Git hooks configured: core.hooksPath = .githooks"
echo "Checking Oracle source encoding..."
echo

if run_python cp1251_to_utf8.py --check "$repository_root"; then
    echo
    echo "Setup completed. Oracle source files use UTF-8."
    exit 0
fi

status=$?
echo >&2
echo "Hooks were configured, but the repository check failed." >&2
if [ "$status" -eq 1 ]; then
    echo "Preview: run the converter without --apply." >&2
    echo "Convert: run the converter with --apply, inspect git diff, then git add." >&2
fi
exit "$status"
