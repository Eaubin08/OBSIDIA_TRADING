#Requires -Version 5.1
<#
    Cockpit V2 Phase A7 — installation locale, sans PYTHONPATH manuel.
    Peut etre lance depuis n'importe quel dossier courant : la racine du
    repo est resolue depuis l'emplacement de ce script.
#>
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Write-Host "Repo root: $RepoRoot"
Set-Location $RepoRoot

$VenvPath = Join-Path $RepoRoot ".venv"
if (-not (Test-Path $VenvPath)) {
    Write-Host "Creation du venv..."
    python -m venv $VenvPath
    if ($LASTEXITCODE -ne 0) { throw "Echec de la creation du venv (python -m venv)." }
} else {
    Write-Host "venv deja present : $VenvPath"
}

$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) { throw "Python introuvable dans le venv : $VenvPython" }

Write-Host "Installation des dependances (requirements.txt)..."
& $VenvPython -m pip install --quiet --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Echec de la mise a jour de pip." }
& $VenvPython -m pip install --quiet -r (Join-Path $RepoRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Echec de l'installation de requirements.txt." }

Write-Host "Installation du projet local en mode editable (pip install -e .)..."
& $VenvPython -m pip install --quiet -e $RepoRoot
if ($LASTEXITCODE -ne 0) { throw "Echec de l'installation editable (pyproject.toml)." }

Write-Host ""
Write-Host "Setup termine. Prochaine etape : .\scripts\verify_install.ps1"
