<#
.SYNOPSIS
  Tache planifiee : sauvegarde du substrat toutes les N minutes vers un second support.
.EXAMPLE
  .\install_backup.ps1 -Dest E:\aethercore-backup
#>
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Dest, [int]$IntervalMinutes=30,
      [string]$TaskName="MultiServiceAI-Backup")
$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent $PSScriptRoot
$action = New-ScheduledTaskAction -Execute "python.exe" `
    -Argument "-m multiservice.backup --dest `"$Dest`"" -WorkingDirectory $proj
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "Sauvegarde locale du substrat MultiService AI (O1b)." -Force | Out-Null
Write-Host "[OK] tache '$TaskName' : toutes les $IntervalMinutes min -> $Dest"
Write-Host "     Verifie de temps en temps : .\scripts\backup.ps1 -Dest `"$Dest`" -Verify"
