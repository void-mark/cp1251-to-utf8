# Repository bootstrap for Windows PowerShell 5.1+ and PowerShell 7+.
# The file intentionally contains ASCII text only, so it works without a BOM.

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

function Get-PythonLauncher {
    $candidates = @(
        [PSCustomObject]@{ Name = "py";      Prefix = @("-3") },
        [PSCustomObject]@{ Name = "python3"; Prefix = @() },
        [PSCustomObject]@{ Name = "python";  Prefix = @() }
    )

    foreach ($candidate in $candidates) {
        $command = Get-Command $candidate.Name -ErrorAction SilentlyContinue
        if ($null -eq $command) {
            continue
        }

        $versionArguments = @()
        $versionArguments += $candidate.Prefix
        $versionArguments += @(
            "-c",
            "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)"
        )

        & $command.Source @versionArguments 2>$null
        if ($LASTEXITCODE -eq 0) {
            return [PSCustomObject]@{
                FilePath = $command.Source
                PrefixArguments = $candidate.Prefix
            }
        }
    }

    return $null
}

$gitCommand = Get-Command git -ErrorAction SilentlyContinue
if ($null -eq $gitCommand) {
    [Console]::Error.WriteLine("Setup failed: Git was not found in PATH.")
    exit 2
}

$pythonLauncher = Get-PythonLauncher
if ($null -eq $pythonLauncher) {
    [Console]::Error.WriteLine("Setup failed: Python 3.9+ was not found. Install Python and enable the py launcher or add Python to PATH.")
    exit 2
}

$parentDirectory = Join-Path -Path $PSScriptRoot -ChildPath ".."
$repositoryRoot = & $gitCommand.Source -C $parentDirectory rev-parse --show-toplevel
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($repositoryRoot)) {
    [Console]::Error.WriteLine("Setup failed: cannot locate the Git repository root.")
    exit 2
}
$repositoryRoot = $repositoryRoot.Trim()

Set-Location -LiteralPath $repositoryRoot

if (-not (Test-Path -LiteralPath ".githooks/pre-commit" -PathType Leaf)) {
    [Console]::Error.WriteLine("Setup failed: .githooks/pre-commit was not found.")
    exit 2
}

if (-not (Test-Path -LiteralPath "cp1251_to_utf8.py" -PathType Leaf)) {
    [Console]::Error.WriteLine("Setup failed: cp1251_to_utf8.py was not found.")
    exit 2
}

$currentHooksPath = & $gitCommand.Source config --get core.hooksPath 2>$null
$hooksQueryExitCode = $LASTEXITCODE
if ($hooksQueryExitCode -ne 0) {
    $currentHooksPath = $null
}

if (
    -not [string]::IsNullOrWhiteSpace($currentHooksPath) -and
    $currentHooksPath.Trim() -ne ".githooks"
) {
    [Console]::Error.WriteLine("Setup stopped: core.hooksPath is already '$($currentHooksPath.Trim())'. Merge the existing hooks with .githooks manually.")
    exit 2
}

& $gitCommand.Source config --local core.hooksPath .githooks
if ($LASTEXITCODE -ne 0) {
    [Console]::Error.WriteLine("Setup failed: cannot configure core.hooksPath.")
    exit 2
}

Write-Host "Git hooks configured: core.hooksPath = .githooks"
Write-Host "Checking Oracle source encoding..."
Write-Host ""

$checkArguments = @()
$checkArguments += $pythonLauncher.PrefixArguments
$checkArguments += @(
    "cp1251_to_utf8.py",
    "--check",
    $repositoryRoot
)

& $pythonLauncher.FilePath @checkArguments
$checkExitCode = $LASTEXITCODE

if ($checkExitCode -eq 0) {
    Write-Host ""
    Write-Host "Setup completed. Oracle source files use UTF-8."
    exit 0
}

[Console]::Error.WriteLine("Hooks were configured, but the repository encoding check failed with exit code $checkExitCode.")
if ($checkExitCode -eq 1) {
    Write-Host "Preview:  py -3 cp1251_to_utf8.py ."
    Write-Host "Convert:  py -3 cp1251_to_utf8.py --apply ."
    Write-Host "Then inspect git diff and stage the converted files again."
}
exit $checkExitCode
