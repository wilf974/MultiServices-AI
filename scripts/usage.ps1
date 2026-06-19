<#
.SYNOPSIS
  Usage S15 (lecture seule) : digest tokens par modele + sessions a fort re-envoi.
.DESCRIPTION
  Lance python -m multiservice.economy. Args optionnels : --pct 0.5 --min-input 1000
#>
$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent $PSScriptRoot
Set-Location $proj
python -m multiservice.economy @args
Write-Host ""
Read-Host "Appuie sur Entree pour fermer"
