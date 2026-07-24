<#
    Rafraichit l'index semantique du central SANS jamais l'indexer sur le VPS.

    Principe (decision 24/07/2026) : INDEXER est lourd et reste sur ce poste ; SERVIR est leger
    et reste au central. Ce script fait le delta local puis pousse le resultat.

      1. copie du journal central vers le poste (LECTURE SEULE : aucune ecriture au central,
         aucune fusion - pour cela c'est scripts\sync_memory_merge.ps1 qui fait foi)
      2. indexation INCREMENTALE locale (ONNX MiniLM, CPU/GPU du poste)
      3. envoi de l'index au central

    Le conteneur voit le nouvel index SANS redemarrage (shared_store invalide sur mtime+taille).

    Usage :  pwsh scripts\refresh_index_vps.ps1
             pwsh scripts\refresh_index_vps.ps1 -DryRun
#>
# L'infra est une donnee de DEPLOIEMENT, jamais du depot (decision 27ff345) : renseignez-la par
# variables d'environnement (ou -VpsUser/-VpsHost/-VpsPort a l'appel).
#   $env:MEM_VPS_USER="<user>"; $env:MEM_VPS_HOST="<hote>"; $env:MEM_VPS_PORT="22"
param(
    [string]$VpsUser   = $(if ($env:MEM_VPS_USER) { $env:MEM_VPS_USER } else { "" }),
    [string]$VpsHost   = $(if ($env:MEM_VPS_HOST) { $env:MEM_VPS_HOST } else { "" }),
    [int]   $VpsPort   = $(if ($env:MEM_VPS_PORT) { [int]$env:MEM_VPS_PORT } else { 22 }),
    [string]$Store     = "$env:USERPROFILE\.aethercore\embeddings-minilm.jsonl",
    [int]   $Threads   = 8,
    [switch]$DryRun
)

if (-not $VpsUser -or -not $VpsHost) {
    throw "Hote central non configure. Definissez MEM_VPS_USER et MEM_VPS_HOST (ou passez -VpsUser/-VpsHost)."
}

$ErrorActionPreference = "Stop"
$racine = Split-Path -Parent $PSScriptRoot

$copie = Join-Path $env:TEMP "journal-central-a-indexer.jsonl"
Write-Host "[1/3] copie du journal central (lecture seule)..."
scp -P $VpsPort -q "${VpsUser}@${VpsHost}:~/.aethercore/journal-llm.jsonl" $copie
if ($LASTEXITCODE -ne 0) { throw "echec de la copie du journal central" }

Write-Host "[2/3] indexation incrementale locale (ONNX MiniLM)..."
Push-Location $racine
try {
    python -m multiservice.index --onnx --batch 32 --threads $Threads --store $Store --journal $copie
} finally {
    Pop-Location
}

$taille = (Get-Item $Store).Length / 1MB
Write-Host ("      index local : {0:N1} Mo" -f $taille)

if ($DryRun) {
    Write-Host "[3/3] DryRun : envoi non effectue."
    exit 0
}

Write-Host "[3/3] envoi au central ($VpsHost)..."
scp -P $VpsPort -q $Store "${VpsUser}@${VpsHost}:~/.aethercore/embeddings-minilm.jsonl"
if ($LASTEXITCODE -ne 0) { throw "echec du transfert scp" }

# Controle de couverture cote central (lecture seule, ne declenche AUCUNE indexation).
$verif = @'
from multiservice import config, memory
from multiservice.journal import read_events
from multiservice.semantic import EmbeddingStore
c = memory.index_coverage(read_events(config.JOURNAL_PATH), EmbeddingStore(config.EMBED_PATH).load())
print("couverture centrale : %d/%d (%.1f%%)" % (c["indexed"], c["eligible"], c["covered_pct"]))
'@
$verif | ssh -p $VpsPort "${VpsUser}@${VpsHost}" "docker exec -i mem-mcp python -"
Write-Host "OK. Le conteneur voit le nouvel index sans redemarrage."
