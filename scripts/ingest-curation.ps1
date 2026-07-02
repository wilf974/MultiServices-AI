# Ingest des decisions de cadrage de l'IA de curation (Phase 0/1) - 02/07/2026.
# Auto-suffisant (env reposees depuis C:\mem a chaque appel) ; a lancer par WILFRED (C1).
# Les 2 corrections visent les sessions des decisions d'origine -> supersede C3 structurel :
#   d9d7e19c (21/06, session suite-observation) et ef345f29 (20/06, session observation).

$env:MEM_INGEST_URL = "https://mem.example.com/ingest"
$env:MEM_CLIENT_CERT = "C:\mem\client.crt"
$env:MEM_CLIENT_KEY = "C:\mem\client.key"
$env:MEM_HMAC_KEY = (Get-Content C:\mem\hmac.key -Raw).Trim()

Write-Host "[1/3] Correction C3 -> session suite-observation (leve d9d7e19c)"
memlog-http "Levee de la periode d'observation (decision du 21/06) : le signal reel est atteint (~130 decisions / ~45 corrections sur 30 j, 705 events/14 j multi-projets). La couche d'intelligence demarre par la CURATION en Phase 1 LECTURE SEULE (detecteurs deterministes, rapports, propositions pending_human) - cadrage <user> 02/07, docs/curation/ + spec 2026-07-02-curation-memoire-design.md." --kind correction --session "suite-observation"

Write-Host "[2/3] Correction C3 -> session observation (leve ef345f29)"
memlog-http "Levee de la periode d'observation (decision jumelle du 20/06) : signal reel atteint, curation Phase 1 lecture seule lancee le 02/07 (voir session suite-observation et session curation-memoire)." --kind correction --session "observation"

Write-Host "[3/3] Decision -> session curation-memoire"
memlog-http "IA de curation de la memoire - Phase 1 LIVREE (lecture seule) : multiservice/curator.py (detecteurs deterministes purs : doublons exacts/proches, gabarits encore valides, decisions anciennes non revisitees, contradictions candidates), rapport borne (k, compteurs complets, truncated), propositions pending_human (schema Phase 2, AUCUNE ecriture), outil MCP curation(source,k,older_than_days). LLM = local Ollama seulement (souverainete), deterministe d'abord. Seuils par defaut (near 0.85, contradiction 0.5, stale 30 j) a recalibrer sur le premier rapport reel (BITS). 299 tests verts (11 nouveaux). Echeance socle 07/07 couverte." --kind decision --session "curation-memoire"

Write-Host ""
Write-Host "Attendu : 3x '201 {id..., source: project:maison}'."
Write-Host "CONTROLE (L-14) : verifier ensuite dans Claude -> recent(1) doit montrer les 3 events."
