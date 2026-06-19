<#
.SYNOPSIS
  Re-indexe les embeddings du journal (D14, incremental) + log minimal.
.DESCRIPTION
  Worker appele par la tache planifiee (install_index.ps1) ou a la main.
  Incremental : n'embed que les nouveaux evenements. Ne touche jamais aethercore.
#>
$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent $PSScriptRoot
Set-Location $proj
$py = "C:\Python313\python.exe"          # chemin absolu (cf. lecon MCP : pas de PATH herite)
$log = Join-Path $proj "logs\index.log"
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
$stamp = Get-Date -Format "o"
# *>&1 capture stdout+stderr ; Tee = console + log. Append-only sur le log.
& $py -m multiservice.index *>&1 | ForEach-Object { "$stamp  $_" } | Tee-Object -FilePath $log -Append
