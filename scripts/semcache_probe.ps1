<#
.SYNOPSIS
  Sonde de calibration du cache semantique (S18) : mesure les quasi-doublons reels du journal.
.DESCRIPTION
  Lecture seule. Embedding local (Ollama). Affiche la distribution des cosinus entre prompts
  et le nombre de paires quasi-identiques par seuil -> aide a fixer le seuil du cache.
  Pre-requis : Ollama lance + modele d'embedding present (ollama pull bge-m3).
#>
$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent $PSScriptRoot
Set-Location $proj
$py = "C:\Python313\python.exe"   # chemin absolu (lecon MCP : pas de PATH herite)
& $py -m multiservice.semcache_probe
