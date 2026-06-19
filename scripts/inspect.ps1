<#
.SYNOPSIS
  Observabilite d'usage LLM (lecture seule) - raccourci.
.DESCRIPTION
  Lance `python -m multiservice.inspect` sur le journal LLM par defaut.
  Double-clic possible (la fenetre reste ouverte). Args optionnels transmis,
  ex: .\inspect.ps1 --journal "C:\autre\journal.jsonl"
#>
$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent $PSScriptRoot   # racine du projet (parent de scripts\)
Set-Location $proj
python -m multiservice.inspect @args
Write-Host ""
Read-Host "Appuie sur Entree pour fermer"
