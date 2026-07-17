<#
.SYNOPSIS
  Rattrape la projection SQLite (Phase 2) + synchronise le canal vectoriel binaire. Log minimal.
.DESCRIPTION
  Worker appele par la tache planifiee (install_project_update.ps1) ou a la main.
  1) run_once : applique au fil de l'eau les lignes du journal a la projection (incremental,
     rebuild force si prefixe divergent — herite de Projection.update). N'ecrit JAMAIS le journal.
  2) --vectors : reconcilie la table binaire `vecs` avec l'EmbeddingStore (apres la tache d'index).
  Evite l'etat STALE constate a chaque reprise de session (journal avance, projection a la traine).
#>
$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent $PSScriptRoot
Set-Location $proj
$py = "C:\Python313\python.exe"          # chemin absolu (cf. lecon MCP : pas de PATH herite)
$log = Join-Path $proj "logs\project.log"
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
$stamp = Get-Date -Format "o"
# *>&1 capture stdout+stderr ; Tee = console + log. Append-only sur le log.
& $py -m multiservice.project *>&1 | ForEach-Object { "$stamp  $_" } | Tee-Object -FilePath $log -Append
& $py -m multiservice.project --vectors *>&1 | ForEach-Object { "$stamp  $_" } | Tee-Object -FilePath $log -Append
