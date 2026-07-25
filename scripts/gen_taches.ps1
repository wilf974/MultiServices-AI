<#
    Genere les commandes .cmd des taches planifiees, pour CETTE machine.

    Pourquoi un generateur plutot que des fichiers versionnes : ces .cmd portent des chemins
    ABSOLUS (racine du projet, interpreteur Python). C'est une donnee de DEPLOIEMENT, jamais du
    depot - meme raison que pour les hotes (decision 27ff345). `scripts/taches/` est gitignore.

    Les taches sont lancees SANS FENETRE par scripts\run_hidden.vbs, qui prend UN argument :
    le chemin d'un .cmd (wscript retire les guillemets internes des arguments, donc passer une
    ligne de commande complete casse des qu'elle contient un chemin entre guillemets).

    Usage :  pwsh scripts\gen_taches.ps1
             pwsh scripts\gen_taches.ps1 -Python "C:\Python313\python.exe"
#>
param(
    [string]$Python = $(if ((Get-Command python -ErrorAction SilentlyContinue)) { (Get-Command python).Source } else { "python.exe" }),
    [string]$Pwsh   = $(if ((Get-Command pwsh   -ErrorAction SilentlyContinue)) { (Get-Command pwsh).Source   } else { "pwsh.exe"   }),
    # Hote central : donnee de DEPLOIEMENT. Elle atterrit dans les .cmd (gitignores), jamais
    # dans le depot. Passez-la ici ou via MEM_VPS_USER / MEM_VPS_HOST / MEM_VPS_PORT.
    [string]$VpsUser = $env:MEM_VPS_USER,
    [string]$VpsHost = $env:MEM_VPS_HOST,
    [string]$VpsPort = $(if ($env:MEM_VPS_PORT) { $env:MEM_VPS_PORT } else { "22" })
)

$ErrorActionPreference = "Stop"
$racine = Split-Path -Parent $PSScriptRoot
$dossier = Join-Path $racine "scripts\taches"
New-Item -ItemType Directory -Force $dossier | Out-Null
New-Item -ItemType Directory -Force (Join-Path $racine "logs") | Out-Null

# nom -> commande (sans redirection : elle est ajoutee ci-dessous, avec l'horodatage)
$taches = [ordered]@{
    "curation_report"  = '"{0}" -m multiservice.curation_report' -f $Python
    "reindex_local"    = '"{0}" -m multiservice.maintenance'     -f $Python
    "sync_merge"       = '"{0}" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{1}\scripts\sync_memory_scheduled.ps1"' -f $Pwsh, $racine
    "refresh_index_vps"= '"{0}" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{1}\scripts\refresh_index_vps.ps1"'     -f $Pwsh, $racine
    # Jugement LLM de curation : > 10 min (43 paires x modele local 35B). HEBDOMADAIRE, jamais
    # synchrone. C'est LUI qui transforme un SIGNALEMENT en PROPOSITION actionnable — sans lui,
    # le rapport quotidien signale du travail sans jamais rien proposer (constat du 25/07).
    "curation_llm"     = '"{0}" -m multiservice.curation_llm' -f $Python
}

foreach ($nom in $taches.Keys) {
    # sync_merge journalise deja en detail dans sync-merge.log : on garde un nom distinct pour
    # ne pas confondre le journal METIER et la trace de la TACHE.
    $log = Join-Path $racine ("logs\{0}{1}.log" -f $nom, $(if ($nom -eq "sync_merge") { ".task" } else { "" }))
    # Les taches qui parlent au central portent l'infra en variables d'environnement locales.
    $env_infra = @()
    if ($nom -in @("refresh_index_vps", "sync_merge") -and $VpsUser -and $VpsHost) {
        $env_infra = @(("set MEM_VPS_USER={0}" -f $VpsUser),
                       ("set MEM_VPS_HOST={0}" -f $VpsHost),
                       ("set MEM_VPS_PORT={0}" -f $VpsPort))
    }
    $lignes = @(
        '@echo off',
        ("rem Commande de la tache MSIA_{0}, lancee SANS FENETRE par scripts\run_hidden.vbs." -f $nom),
        'rem GENERE par scripts\gen_taches.ps1 - ne pas editer a la main, ne pas committer.',
        ('pushd "{0}"' -f $racine)
    ) + $env_infra + @(
        ('echo. >> "{0}"' -f $log),
        ('echo ===== %DATE% %TIME% ===== >> "{0}"' -f $log),
        ('{0} >> "{1}" 2>&1' -f $taches[$nom], $log),
        ('echo [code retour %ERRORLEVEL%] >> "{0}"' -f $log),
        'popd'
    )
    $cible = Join-Path $dossier "$nom.cmd"
    Set-Content -Path $cible -Value $lignes -Encoding ASCII
    Write-Host ("genere : scripts\taches\{0}.cmd" -f $nom)
}

Write-Host ""
Write-Host "Action a declarer dans le planificateur, pour chaque tache :"
Write-Host ('  wscript.exe "{0}\scripts\run_hidden.vbs" "{0}\scripts\taches\<nom>.cmd"' -f $racine)
