<#
.SYNOPSIS
  Replication append-only du journal-verite AetherCore vers un second support LOCAL.

.DESCRIPTION
  Assurance la moins chere contre la perte de la memoire (cf. DECISIONS.md O1b) :
  le journal vit sur le Poste Windows (le SPOF). On en garde une copie sur un
  SECOND support physique (cle/disque USB).

  - Replication EXTERNE, JAMAIS write-through : ce script ne touche pas a l'ecriture
    primaire, il ne fait que copier. Aucun risque de bloquer le journal.
  - robocopy SANS /MIR : on n'efface jamais dans la destination (append-only respecte).
  - Le journal est petit (quelques Mo) : le recopier en entier ne coute rien. Le jour
    ou il grossit, passer a rsync via WSL (lignes neuves seulement).

.PARAMETER Dest
  Dossier de destination sur le SECOND support (ex: E:\aethercore-backup).

.PARAMETER Source
  Dossier du journal (defaut: %USERPROFILE%\.aethercore).

.EXAMPLE
  .\replicate_journal.ps1 -Dest E:\aethercore-backup
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $Dest,
    [string] $Source = (Join-Path $env:USERPROFILE ".aethercore"),
    [string] $Pattern = "*.jsonl"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Source)) {
    Write-Host "[ERREUR] Source introuvable : $Source"
    exit 1
}

# Garde-fou honnete : un second dossier sur le MEME disque ne survit pas a une
# panne de disque/machine. On avertit si la destination est sur le meme lecteur.
$srcRoot = [System.IO.Path]::GetPathRoot((Resolve-Path $Source).Path)
$destRoot = [System.IO.Path]::GetPathRoot([System.IO.Path]::GetFullPath($Dest))
if ($srcRoot -eq $destRoot) {
    Write-Host "[AVERTISSEMENT] Destination sur le meme lecteur que la source ($destRoot)."
    Write-Host "                Une panne de disque emporte les deux. Utilise un support PHYSIQUE distinct."
}

if (-not (Test-Path $Dest)) { New-Item -ItemType Directory -Path $Dest -Force | Out-Null }

$logDir = Join-Path $Dest "_logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$log = Join-Path $logDir "replicate-$stamp.log"

# /COPY:DAT donnees+attributs+horodatage ; /R:2 /W:2 reprises rapides ;
# PAS de /MIR (jamais d'effacement). /NP propre en log.
robocopy $Source $Dest $Pattern /COPY:DAT /R:2 /W:2 /NP /LOG:$log | Out-Null
$rc = $LASTEXITCODE

# robocopy : codes 0-7 = succes (>=8 = erreur reelle).
if ($rc -ge 8) {
    Write-Host "[ECHEC] robocopy code $rc - voir $log"
    exit $rc
}
Write-Host "[OK] journal replique vers $Dest (robocopy code $rc) - $stamp"
exit 0
