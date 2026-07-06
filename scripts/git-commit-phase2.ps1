# Commit de la Phase 2 curation (cloture ciblee + file journal-as-queue) - 02/07/2026 soir.
# LANCER DEPUIS WINDOWS :
#   powershell -ExecutionPolicy Bypass -File "C:\Users\<user>\Claude\Projects\MultiService IA\scripts\git-commit-phase2.ps1"
# Meme protocole que git-commit-session.ps1 (v2.1) : log transcript, gate pytest, idempotent.

$ErrorActionPreference = "Continue"
$repo = "C:\Users\<user>\Claude\Projects\MultiService IA"
try { Start-Transcript -Path (Join-Path $repo "scripts\git-commit-phase2.log") -Force | Out-Null } catch {}

function Done([int]$code) {
    try { Stop-Transcript | Out-Null } catch {}
    Write-Host ""
    Read-Host "Appuie sur Entree pour fermer (log: scripts\git-commit-phase2.log)"
    exit $code
}
function Fail([string]$msg) { Write-Host "ABORT: $msg"; Done 1 }

if (-not (Test-Path (Join-Path $repo ".git"))) { Fail "repo introuvable: $repo" }
Set-Location $repo
$branch = git rev-parse --abbrev-ref HEAD
if ($LASTEXITCODE -ne 0) { Fail "git indisponible." }
if ($branch -ne "feature/routeur-multi-fournisseurs") {
    Fail "branche courante '$branch' (attendu feature/routeur-multi-fournisseurs)."
}
if (Test-Path ".git\index.lock") { Fail ".git\index.lock present. Si aucun git ne tourne : Remove-Item '.git\index.lock'" }

Write-Host "[gate] pytest (attendu : 315 passed)..."
if (Get-Command python -ErrorAction SilentlyContinue) { python -m pytest -q tests }
elseif (Get-Command pytest -ErrorAction SilentlyContinue) { pytest -q tests }
else { Fail "ni 'python' ni 'pytest' sur le PATH." }
if ($LASTEXITCODE -ne 0) { Fail "tests en echec, rien n'est commite." }

git add multiservice/memory.py multiservice/curator.py multiservice/memlog_http.py `
        multiservice/ingest.py tests/test_curation_closes.py tests/test_memlog_http.py `
        tests/test_ingest.py `
        docs/superpowers/specs/2026-07-02-curation-memoire-design.md `
        docs/superpowers/plans/2026-07-02-curation-memoire.md `
        scripts/git-commit-phase2.ps1
if ($LASTEXITCODE -ne 0) { Fail "git add a echoue." }
git diff --cached --quiet
if ($LASTEXITCODE -eq 0) { Write-Host "(rien a committer - deja fait)"; }
else {
    git commit -m "feat(curation): Phase 2 - cloture CIBLEE data.closes=[ids] (session neutre curation-closures, honoree par recall/recall_semantic/lessons et les detecteurs) + file journal-as-queue (command/command_reject portes par chaque proposition, rejets data.rejects) + canal memlog-http --closes/--rejects signes + validation ingest 422. Le design 'session de l'original' etait fautif (aurait perime l'original a garder) - corrige avant de coder, prouve par test. 315 tests verts (11 nouveaux)."
    if ($LASTEXITCODE -ne 0) { Fail "git commit a echoue." }
}

Write-Host "[push]..."
git push origin feature/routeur-multi-fournisseurs
if ($LASTEXITCODE -ne 0) { Write-Host "Push KO - relancer : git push origin feature/routeur-multi-fournisseurs"; Done 1 }

git log --oneline -3
Write-Host ""
Write-Host "OK. Suites : pip --force-reinstall postes (@feature/...), redeployer mem-mcp + mem-ingest,"
Write-Host "redemarrer Claude Desktop, puis coller les 2 commandes d'approbation des propositions."
Done 0
