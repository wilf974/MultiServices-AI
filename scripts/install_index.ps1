<#
.SYNOPSIS
  Tache planifiee : re-indexation des embeddings (D14) toutes les N minutes (incremental).
.DESCRIPTION
  Garde le recall semantique frais sans relance manuelle. Lance scripts\index.ps1.
  Incremental + local (Ollama) ; ne touche jamais aethercore.
.EXAMPLE
  .\install_index.ps1                 # toutes les 30 min
  .\install_index.ps1 -IntervalMinutes 15
#>
[CmdletBinding()]
param([int]$IntervalMinutes = 30, [string]$TaskName = "MultiServiceAI-Index")
$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent $PSScriptRoot
$worker = Join-Path $PSScriptRoot "index.ps1"
if (-not (Test-Path $worker)) { throw "introuvable : $worker" }

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$worker`"" `
    -WorkingDirectory $proj
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "Re-indexation incrementale des embeddings MultiService AI (D14)." `
    -Force | Out-Null
Write-Host "[OK] tache '$TaskName' : reindex toutes les $IntervalMinutes min."
Write-Host "     Log : $proj\logs\index.log"
Write-Host "     Run manuel : .\scripts\index.ps1"
