#Requires -Version 5.1
<#
    Cockpit V2 Phase A7 — verification d'installation locale UNIQUEMENT.
    Ne verifie jamais l'accessibilite du vrai Kernel X-108 ni du marche
    Alpaca reel : ce sont des prerequis runtime EXTERNES, rapportes
    separement, pas une condition de validite de l'installation locale.
#>
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    throw "venv introuvable. Lancez d'abord .\scripts\setup_windows.ps1"
}

function Check($label, $scriptBlock) {
    Write-Host -NoNewline "[ ] $label ... "
    try {
        & $scriptBlock
        if ($LASTEXITCODE -ne 0) { throw "exit code $LASTEXITCODE" }
        Write-Host "OK"
    } catch {
        Write-Host "ECHEC"
        throw "Verification echouee : $label -- $_"
    }
}

Check "Python fonctionne" { & $VenvPython --version }
Check "Import apps (package local)" { & $VenvPython -c "import apps" }
Check "Import Streamlit" { & $VenvPython -c "import streamlit" }
Check "Import Cockpit V2" { & $VenvPython -c "import apps.cockpit_v2.app" }
Check "Tests non-reseau (Cockpit V2 + boundaries + trace)" {
    & $VenvPython -m pytest tests/unit/test_cockpit_v2_presenter.py tests/unit/test_cockpit_v2_boundaries.py tests/unit/test_obsidia_trace_flag.py -q
}

Write-Host ""
Write-Host "Installation locale : VALIDE."
Write-Host ""
Write-Host "Prerequis runtime EXTERNES (non verifies ici, requis pour le Reference Runtime uniquement) :"
Write-Host "  - fichier .env avec ALPACA_API_KEY / ALPACA_SECRET_KEY (paper trading)"
Write-Host "  - Kernel X-108 reel accessible (server.kernel.sealed.cjs, port 3001) pour un vrai round-trip"
Write-Host ""
Write-Host "Prochaine etape : .\scripts\run_cockpit.ps1"
