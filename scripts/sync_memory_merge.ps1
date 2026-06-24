<#
.SYNOPSIS
  Bidirectional, lossless MERGE of the MultiService IA memory journal between this
  Windows machine and the Linux VM. Replaces the old one-way overwrite sync.

.DESCRIPTION
  The journal is append-only JSONL with unique event ids. Merging = union by id
  (multiservice.sync.merge_journal): it only APPENDS missing events, never rewrites
  or deletes -> safe and idempotent. Both machines can write their own journal; this
  script reconciles them so both ends converge to the same union.

  Flow:
    1. Snapshot both journals (timestamped .bak, belt-and-suspenders).
    2. Pull VM journal -> merge into Windows journal (adds VM-only events here).
    3. Push merged Windows journal -> merge into VM journal (adds Windows-only events there).
    4. Verify both sides hold the same event count.

  ASCII-only output (project rule: PowerShell console encoding).

.EXAMPLE
  pwsh scripts/sync_memory_merge.ps1
#>

$ErrorActionPreference = "Stop"

$VpsHost   = "adminvps@192.168.1.210"
$VpsPort   = "2299"
$WinJournal = Join-Path $HOME ".aethercore\journal-llm.jsonl"
$VmJournal  = "/home/adminvps/.aethercore/journal-llm.jsonl"
$VmPy       = "/home/adminvps/multiservice/.venv/bin/python"
$ProjDir    = Split-Path -Parent $PSScriptRoot   # repo root (scripts/..)
$Stamp      = (Get-Date -Format "yyyyMMdd-HHmmss")
$Tmp        = [System.IO.Path]::GetTempPath()

function Count-Local($path) {
    if (-not (Test-Path $path)) { return 0 }
    (Get-Content -LiteralPath $path | Where-Object { $_.Trim() -ne "" }).Count
}

Write-Output "[merge] Windows journal: $WinJournal"
Write-Output "[merge] VM journal     : ${VpsHost}:${VmJournal}"

# --- 1. Snapshots ---
if (Test-Path $WinJournal) {
    Copy-Item -LiteralPath $WinJournal -Destination "$WinJournal.bak-$Stamp"
    Write-Output "[merge] snapshot win -> $WinJournal.bak-$Stamp"
}
ssh -p $VpsPort -o BatchMode=yes $VpsHost "cp -n '$VmJournal' '$VmJournal.bak-$Stamp' 2>/dev/null; cp '$VmJournal' '$VmJournal.bak-$Stamp'" | Out-Null
Write-Output "[merge] snapshot vm  -> $VmJournal.bak-$Stamp"

$beforeWin = Count-Local $WinJournal
$beforeVm  = [int](ssh -p $VpsPort -o BatchMode=yes $VpsHost "grep -c . '$VmJournal' 2>/dev/null || echo 0")
Write-Output "[merge] before: win=$beforeWin  vm=$beforeVm"

# --- 2. Pull VM journal, merge into Windows ---
$pulledVm = Join-Path $Tmp "vm-journal-$Stamp.jsonl"
scp -P $VpsPort -o BatchMode=yes "${VpsHost}:${VmJournal}" $pulledVm | Out-Null
Push-Location $ProjDir
python -m multiservice.sync --from $pulledVm --to $WinJournal
Pop-Location

# --- 3. Push merged Windows journal, merge into VM ---
$pushedWin = "/tmp/win-journal-$Stamp.jsonl"
scp -P $VpsPort -o BatchMode=yes $WinJournal "${VpsHost}:${pushedWin}" | Out-Null
ssh -p $VpsPort -o BatchMode=yes $VpsHost "$VmPy -m multiservice.sync --from '$pushedWin' --to '$VmJournal'"

# --- 4. Verify convergence ---
$afterWin = Count-Local $WinJournal
$afterVm  = [int](ssh -p $VpsPort -o BatchMode=yes $VpsHost "grep -c . '$VmJournal' 2>/dev/null || echo 0")
Write-Output "[merge] after : win=$afterWin  vm=$afterVm"

# Cleanup temp transfer files (keep .bak snapshots).
Remove-Item -LiteralPath $pulledVm -ErrorAction SilentlyContinue
ssh -p $VpsPort -o BatchMode=yes $VpsHost "rm -f '$pushedWin'" | Out-Null

if ($afterWin -eq $afterVm) {
    Write-Output "[merge] OK: both ends converged to $afterWin events."
} else {
    Write-Output "[merge] WARNING: counts differ (win=$afterWin vm=$afterVm). Check snapshots .bak-$Stamp."
    exit 1
}
