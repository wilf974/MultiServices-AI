<#
.SYNOPSIS
  Promotion de skill S17 (human-gated). Tu choisis, tu promeus.
.EXAMPLES
  .\promote.ps1 hfsql-odbc --description "Connecteur HFSQL via ODBC + API v1" --trigger "odbc+hfsql+api" --body-file notes.md
  .\promote.ps1 hfsql-odbc --health --trigger "odbc+hfsql"
  .\promote.ps1 hfsql-odbc --retire --description "remplace par v2"
#>
$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent $PSScriptRoot
Set-Location $proj
python -m multiservice.promote @args
Write-Host ""
Read-Host "Appuie sur Entree pour fermer"
