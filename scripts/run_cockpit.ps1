#Requires -Version 5.1
<#
    Cockpit V2 Phase A7 — lancement, sans PYTHONPATH manuel.
#>
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    throw "venv introuvable. Lancez d'abord .\scripts\setup_windows.ps1"
}

& $VenvPython -m streamlit run (Join-Path $RepoRoot "apps\cockpit_v2\app.py")
