<#
.SYNOPSIS
Build the per-user Windows setup.exe with Inno Setup 6.
.DESCRIPTION
With no PackageDir, first runs build.ps1 using the active Python environment.
Supply -PackageDir to package an already-built folder instead, including an
isolated sibling build when another copy of Lilt is running. Either way, the
whole folder is validated and its noninteractive --self-test must pass.
Paths are relative to this project folder unless absolute.
.EXAMPLE
.\build-installer.ps1
.EXAMPLE
.\build-installer.ps1 -PackageDir .\dist\Lilt-release -CompilerPath 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
#>
[CmdletBinding()]
param(
    [string]$PackageDir,
    [string]$OutputDir = 'dist\installer',
    [string]$CompilerPath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-LiltAbsolutePath([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { throw 'A file or folder path cannot be empty.' }
    if (-not [System.IO.Path]::IsPathRooted($Path)) {
        $Path = Join-Path $PSScriptRoot $Path
    }
    return [System.IO.Path]::GetFullPath($Path)
}

if ([string]::IsNullOrWhiteSpace($CompilerPath)) {
    $liltCompilerCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($liltCompilerCommand) { $CompilerPath = $liltCompilerCommand.Source }
    else {
        $liltCompilerCandidates = @(
            (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
            (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
        )
        foreach ($liltCandidate in $liltCompilerCandidates) {
            if (Test-Path -LiteralPath $liltCandidate -PathType Leaf) {
                $CompilerPath = $liltCandidate
                break
            }
        }
    }
}
if ([string]::IsNullOrWhiteSpace($CompilerPath)) {
    throw 'Inno Setup 6 was not found. Install it from https://jrsoftware.org/isdl.php or pass -CompilerPath to ISCC.exe.'
}
$liltCompiler = Get-LiltAbsolutePath $CompilerPath
if (-not (Test-Path -LiteralPath $liltCompiler -PathType Leaf)) {
    throw "The Inno Setup compiler does not exist: $liltCompiler"
}

$liltVersionSource = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'lilt\__init__.py') -Raw
$liltVersionMatch = [regex]::Match($liltVersionSource, '(?m)^__version__\s*=\s*["''](\d+\.\d+\.\d+)["'']\s*$')
if (-not $liltVersionMatch.Success) { throw 'Could not read a numeric app version from lilt/__init__.py.' }
$liltVersion = $liltVersionMatch.Groups[1].Value

if (-not $PSBoundParameters.ContainsKey('PackageDir')) {
    & (Join-Path $PSScriptRoot 'build.ps1')
    $PackageDir = 'dist\Lilt'
}
$liltPackage = Get-LiltAbsolutePath $PackageDir
$liltOutput = Get-LiltAbsolutePath $OutputDir
if (-not (Test-Path -LiteralPath $liltPackage -PathType Container)) {
    throw "The packaged application folder does not exist: $liltPackage"
}
if ($liltOutput.StartsWith($liltPackage.TrimEnd('\') + '\', [System.StringComparison]::OrdinalIgnoreCase) -or
    $liltOutput.TrimEnd('\').Equals($liltPackage.TrimEnd('\'), [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'OutputDir must be outside PackageDir so the installer cannot include itself.'
}

foreach ($liltRequiredFile in @(
    'Lilt.exe', '_internal\PySide6\Qt6Core.dll', 'README.md',
    'docs\translator.png', 'THIRD_PARTY_NOTICES.md',
    'licenses\GPL-3.0.txt', 'licenses\LGPL-3.0.txt', 'licenses\PYTHON-LICENSE.txt'
)) {
    if (-not (Test-Path -LiteralPath (Join-Path $liltPackage $liltRequiredFile) -PathType Leaf)) {
        throw "The complete application package is required. Missing: $liltRequiredFile"
    }
}
$liltPrivateFiles = Get-ChildItem -LiteralPath $liltPackage -Recurse -File | Where-Object {
    $_.Name -like '*.sqlite3*' -or $_.Name -in @('credentials.dpapi', '.env', 'app.lock')
} | Select-Object -First 1
if ($liltPrivateFiles) { throw "Remove personal data from the package before distribution: $($liltPrivateFiles.Name)" }

$liltTemporaryRoot = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath ([System.IO.Path]::GetTempPath())).Path)
$liltCheckDirectory = Join-Path $liltTemporaryRoot ('Lilt-installer-check-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $liltCheckDirectory | Out-Null
try {
    $liltReportPath = Join-Path $liltCheckDirectory 'package-check.json'
    $liltCheckProcess = Start-Process -FilePath (Join-Path $liltPackage 'Lilt.exe') -WorkingDirectory $liltPackage `
        -ArgumentList @('--self-test', ('"' + $liltReportPath + '"')) -PassThru -WindowStyle Hidden
    if (-not $liltCheckProcess.WaitForExit(30000)) {
        # This is only the isolated check process started above, never a user's app.
        Stop-Process -Id $liltCheckProcess.Id -ErrorAction SilentlyContinue
        throw 'The package self-test did not finish within 30 seconds.'
    }
    if ($liltCheckProcess.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $liltReportPath)) {
        throw 'The packaged application failed its self-test.'
    }
    $liltCheckReport = Get-Content -LiteralPath $liltReportPath -Raw | ConvertFrom-Json
    if (-not $liltCheckReport.ok -or $liltCheckReport.app_version -ne $liltVersion) {
        throw "The packaged application must pass its checks and match source version $liltVersion."
    }
}
finally {
    # Remove only the known report and its empty folder, never a recursive tree.
    if (Test-Path -LiteralPath $liltCheckDirectory) {
        $liltCheckItem = Get-Item -LiteralPath $liltCheckDirectory -Force
        $liltResolvedCheckDirectory = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $liltCheckDirectory).Path)
        $liltResolvedCheckParent = [System.IO.Path]::GetDirectoryName($liltResolvedCheckDirectory)
        if (-not $liltCheckItem.PSIsContainer -or
            ($liltCheckItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -or
            -not $liltResolvedCheckDirectory.Equals($liltCheckDirectory, [System.StringComparison]::OrdinalIgnoreCase) -or
            -not $liltResolvedCheckParent.TrimEnd('\').Equals($liltTemporaryRoot.TrimEnd('\'), [System.StringComparison]::OrdinalIgnoreCase)) {
            throw 'The check folder is outside its intended temporary root or is a link; it was left intact.'
        }
        $liltCleanupReport = Join-Path $liltResolvedCheckDirectory 'package-check.json'
        if (Test-Path -LiteralPath $liltCleanupReport) {
            $liltCleanupReportItem = Get-Item -LiteralPath $liltCleanupReport -Force
            if ($liltCleanupReportItem.PSIsContainer -or
                ($liltCleanupReportItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
                throw 'The check report is not an ordinary file; the temporary folder was left intact.'
            }
            Remove-Item -LiteralPath $liltCleanupReport -Force
        }
        # Delete(path, false) fails safely if any unexpected contents appeared.
        [System.IO.Directory]::Delete($liltResolvedCheckDirectory, $false)
    }
}

New-Item -ItemType Directory -Path $liltOutput -Force | Out-Null
$liltCompilerArguments = @(
    ('/DAppVersion=' + $liltVersion),
    ('/DPackageDir=' + $liltPackage),
    ('/DOutputDir=' + $liltOutput),
    (Join-Path $PSScriptRoot 'installer\Lilt.iss')
)
& $liltCompiler @liltCompilerArguments
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup could not compile the installer.' }
$liltInstaller = Join-Path $liltOutput 'setup.exe'
if (-not (Test-Path -LiteralPath $liltInstaller -PathType Leaf)) { throw 'Inno Setup did not produce setup.exe.' }
Write-Host "Ready: $liltInstaller (Lilt $liltVersion, Windows x64)."
