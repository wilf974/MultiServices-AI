<#
.SYNOPSIS
  Skills emergentes S17 (detection, lecture seule) : patterns de prompts recurrents.
.DESCRIPTION
  Lance python -m multiservice.skills. Args : --min N (recurrence mini, defaut 3)
#>
$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent $PSScriptRoot
Set-Location $proj
python -m multiservice.skills @args
Write-Host ""
Read-Host "Appuie sur Entree pour fermer"
