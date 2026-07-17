<#
.SYNOPSIS
  Tache planifiee : rattrapage incremental de la projection SQLite toutes les N minutes.
.DESCRIPTION
  Garde la projection FRESH sans relance manuelle (l'etat STALE journal/projection etait
  constate a chaque reprise de session). Lance scripts\project_update.ps1 (run_once + --vectors).
  Lecture du journal seulement ; n'ecrit jamais le journal.
.EXAMPLE
  .\install_project_update.ps1                 # toutes les 15 min
  .\install_project_update.ps1 -IntervalMinutes 30
#>
[CmdletBinding()]
param([int]$IntervalMinutes = 15, [string]$TaskName = "MultiServiceAI-Projection")
$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent $PSScriptRoot
$worker = Join-Path $PSScriptRoot "project_update.ps1"
if (-not (Test-Path $worker)) { throw "introuvable : $worker" }

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$worker`"" `
    -WorkingDirectory $proj
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "Rattrapage incremental de la projection SQLite MultiService AI (Phase 2)." `
    -Force | Out-Null
Write-Host "[OK] tache '$TaskName' : rattrapage projection toutes les $IntervalMinutes min."
Write-Host "     Log : $proj\logs\project.log"
Write-Host "     Run manuel : .\scripts\project_update.ps1"
