<#
.SYNOPSIS
  O1b - sauvegarde locale du substrat (journaux + cache + skills), verifiable.
.EXAMPLES
  .\backup.ps1 -Dest E:\aethercore-backup
  .\backup.ps1 -Dest E:\aethercore-backup -Verify
#>
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Dest, [switch]$Verify)
$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent $PSScriptRoot
Set-Location $proj
if ($Verify) { python -m multiservice.backup --dest $Dest --verify }
else         { python -m multiservice.backup --dest $Dest }
Write-Host ""
Read-Host "Appuie sur Entree pour fermer"
