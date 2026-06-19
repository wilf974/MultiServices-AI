<#
.SYNOPSIS
  Enregistre une tache planifiee qui replique le journal vers un second support.

.DESCRIPTION
  A faire tourner a cote de watch_once.ps1 / briefing_daily.ps1.
  Cadence par defaut : toutes les 15 minutes (le journal est petit, le cout est nul).

.PARAMETER Dest
  Dossier de destination sur le SECOND support physique (ex: E:\aethercore-backup).

.PARAMETER IntervalMinutes
  Periode de replication (defaut 15).

.EXAMPLE
  .\install_journal_replication.ps1 -Dest E:\aethercore-backup
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $Dest,
    [int] $IntervalMinutes = 15,
    [string] $TaskName = "AetherCore-JournalReplication"
)

$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "replicate_journal.ps1"
if (-not (Test-Path $script)) { throw "introuvable : $script" }

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`" -Dest `"$Dest`""

# Repetition toutes les N minutes, indefiniment, a partir de maintenant.
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -DontStopOnIdleEnd -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "Replication append-only du journal AetherCore vers un second support local (DECISIONS O1b)." `
    -Force | Out-Null

Write-Host "[OK] tache '$TaskName' enregistree : toutes les $IntervalMinutes min -> $Dest"
Write-Host "     Verifie : Get-ScheduledTask -TaskName $TaskName"
Write-Host "     Premier run manuel : .\replicate_journal.ps1 -Dest `"$Dest`""
