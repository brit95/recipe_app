# Build the single-file Recipe Manager .exe on Windows.
# Run from the repo's `recipe_app\` directory in PowerShell.

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if (-not (Test-Path ".venv")) {
    Write-Host ">> creating .venv"
    python -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip | Out-Null
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt | Out-Null
& ".\.venv\Scripts\python.exe" -m pip install pyinstaller | Out-Null

Write-Host ">> building"
if (Test-Path build) { Remove-Item -Recurse -Force build }
if (Test-Path dist)  { Remove-Item -Recurse -Force dist }

& ".\.venv\Scripts\pyinstaller.exe" --clean --noconfirm RecipeManager.spec

Write-Host ""
Write-Host "Build complete:"
Get-ChildItem dist | Select-Object Name, Length
Write-Host ""
Write-Host "Run it:  .\dist\RecipeManager.exe"
