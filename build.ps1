$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
python -m pip install -r requirements.txt pyinstaller Pillow
if ($LASTEXITCODE -ne 0) { throw 'Could not install build dependencies.' }
python tools/make_icon.py
if ($LASTEXITCODE -ne 0) { throw 'Could not generate the app icon.' }
python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed. The app was not packaged.' }
python -m PyInstaller --noconfirm --clean Lilt.spec
if ($LASTEXITCODE -ne 0) { throw 'Packaging failed.' }
Copy-Item -LiteralPath README.md -Destination dist/Lilt/README.md -Force
Copy-Item -LiteralPath docs -Destination dist/Lilt -Recurse -Force
python tools/copy_notices.py
if ($LASTEXITCODE -ne 0) { throw 'Could not copy runtime license notices.' }
$liltReportPath = Join-Path $PSScriptRoot 'build\package-check.json'
$liltExePath = Join-Path $PSScriptRoot 'dist\Lilt\Lilt.exe'
$liltPackProcess = Start-Process -FilePath $liltExePath -ArgumentList @('--self-test', ('"' + $liltReportPath + '"')) -PassThru -WindowStyle Hidden
if (-not $liltPackProcess.WaitForExit(30000)) {
    Stop-Process -Id $liltPackProcess.Id -ErrorAction SilentlyContinue
    throw 'The packaged app did not finish its startup check.'
}
if ($liltPackProcess.ExitCode -ne 0) { throw 'The packaged app failed its startup check.' }
$liltReport = Get-Content -LiteralPath $liltReportPath -Raw | ConvertFrom-Json
if (-not $liltReport.ok) { throw 'The packaged app failed its data and interface checks.' }
Write-Host 'Ready: dist\Lilt\Lilt.exe (keep the entire Lilt folder together).'
