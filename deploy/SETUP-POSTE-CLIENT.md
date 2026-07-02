# Setup d'un poste client sur la mémoire centrale MultiService-IA

Brancher un nouveau poste pour **lire** (MCP HTTP) et **écrire** (memlog-http, mTLS) la mémoire centrale.

- Endpoint central : `https://mem.example.com` — lecture `/mcp` (bearer), écriture `/ingest` (mTLS + HMAC).
- **Prérequis** : l'IP publique du poste doit être ajoutée à l'allowlist du vhost `mem.example.com` (sinon 403).
- **Secrets** (NE JAMAIS committer / logger) :
  - `BEARER` (lecture) : dans `/etc/nginx/sites-enabled/mem.example.com` (ligne `map $http_authorization $mem_ok`).
  - `client.crt` / `client.key` / `hmac.key` (écriture) : générés par poste sur le VPS (§2).

---

## 1. Lecture — brancher le MCP (PowerShell **ou** bash, même commande)
```
claude mcp add --transport http multiservice-memory https://mem.example.com/mcp --header "Authorization: Bearer <BEARER>"
```
Vérifier dans le Claude CLI : `/mcp` -> `multiservice-memory connected` (12 outils : recall, recall_semantic, why, replay, replay_event, forecast...). Si le serveur sert en SSE : refaire avec `--transport sse`.

---

## 2. Écriture — générer le cert du poste (sur le VPS, root)
```bash
ssh -p <SSH_PORT> <user>@mem.example.com        # ou <user>@<VPS_LAN> depuis le LAN
NOM=monposte                                # CN unique du poste -> source=project:$NOM
cd /home/<user>/mem-mcp-src
sudo bash deploy/gen-mtls.sh "$NOM" "project:$NOM"
HMAC=$(sudo cat /home/<user>/mem-secrets/clients/$NOM/hmac.key)
# inscrire au registre (cree ou met a jour le JSON) :
sudo python3 -c 'import json,os,sys;p="/home/<user>/mem-secrets/ingest-clients.json";r=json.load(open(p)) if os.path.exists(p) else {};r[sys.argv[1]]={"source":"project:"+sys.argv[1],"hmac_key":sys.argv[2]};json.dump(r,open(p,"w"),indent=2);print("registre ->",list(r))' "$NOM" "$HMAC"
# exposer les 3 fichiers pour scp (compte <user>) :
sudo cp /home/<user>/mem-secrets/clients/$NOM/client.crt /home/<user>/mem-secrets/clients/$NOM/client.key /home/<user>/mem-secrets/clients/$NOM/hmac.key /home/<user>/
sudo chown <user>:<user> /home/<user>/client.crt /home/<user>/client.key /home/<user>/hmac.key
```
Récupérer sur le poste (un `scp` par fichier ; PowerShell ne fait pas l'expansion `{a,b,c}`) :
```
scp -P <SSH_PORT> <user>@mem.example.com:/home/<user>/client.crt <DEST>
scp -P <SSH_PORT> <user>@mem.example.com:/home/<user>/client.key <DEST>
scp -P <SSH_PORT> <user>@mem.example.com:/home/<user>/hmac.key  <DEST>
```
`<DEST>` = `C:\mem` (Windows) ou `~/mem` (Linux). Puis nettoyer le VPS :
```bash
rm /home/<user>/client.crt /home/<user>/client.key /home/<user>/hmac.key
```

---

## 3. Écriture — installer le client
```
pip install "multiservice-ia[ingest] @ git+https://github.com/wilf974/MultiServices-AI.git"
```
(Nom du paquet = `multiservice-ia`, PAS `multiservice`. Pour mettre à jour : ajouter `--force-reinstall --no-deps`.)

---

## 4. Écriture — journaliser (commande auto-suffisante, repose les 4 vars à chaque appel)

### PowerShell (Windows, certs dans `C:\mem`)
```
$env:MEM_INGEST_URL="https://mem.example.com/ingest"; $env:MEM_CLIENT_CERT="C:\mem\client.crt"; $env:MEM_CLIENT_KEY="C:\mem\client.key"; $env:MEM_HMAC_KEY=(Get-Content C:\mem\hmac.key -Raw).Trim(); memlog-http "<FAIT>" --kind <decision|correction|observation|validation|note|hypothesis> --session "<sujet-stable>"
```

### bash (Git Bash / Linux, certs dans `/c/mem` ou `~/mem`)
```
MEM_INGEST_URL="https://mem.example.com/ingest" MEM_CLIENT_CERT="/c/mem/client.crt" MEM_CLIENT_KEY="/c/mem/client.key" MEM_HMAC_KEY="$(tr -d '\r\n' < /c/mem/hmac.key)" memlog-http "<FAIT>" --kind decision --session "<sujet-stable>"
```
(`tr -d '\r\n'` = équivalent bash du `.Trim()` ; sinon la clé a un CRLF -> 401. Si `memlog-http` introuvable en bash : `python -m multiservice.memlog_http`.)

Réponse attendue : `201 {"id":...,"source":"project:<NOM>"}` (la source est imposée par le serveur via le CN du cert ; ne pas la mettre dans le texte).

**Conventions** : `decision`=choix · `correction`=revirement (MÊME `--session` -> péremption C3) · `observation`=fait terrain · `validation`=vérif OK. `--session`=sujet stable. Texte autoportant, ASCII de préférence.

**Garde anti-gabarit (01/07/2026)** : un texte de gabarit non rempli (ex. `<FAIT>`, `<le fait, texte reel>` — comme dans les exemples ci-dessus !) est **refusé** : exit 2 côté client, `422 placeholder text` côté serveur. Contournement volontaire : `--force` (voyage dans le corps signé). Pollution observée au journal → `multiservice/hygiene.py`.

**Codes** : `201` OK · `401` signature/cert · `403` mTLS/IP non allowlistée · `409` rejeu · `422` format ou gabarit non rempli.

---

## 5. Windows uniquement — réparer les hooks du Claude CLI (`python3`)
Les hooks tournent en **Git Bash** et appellent `python3`, absent de python.org (seul `python.exe`).
```powershell
# 1) Parametres > Applications > Parametres avances > Alias d'execution d'applications
#    -> desactiver python.exe ET python3.exe
# 2) creer un vrai python3 a cote de python (dossier Python sur le PATH) :
Copy-Item "C:\Users\<USER>\AppData\Local\Programs\Python\Python311\python.exe" "C:\Users\<USER>\AppData\Local\Programs\Python\Python311\python3.exe"
# 3) verifier en Git Bash : python3 --version  ; puis relancer le Claude CLI
```
Relancer le Claude CLI seul ne suffit pas (PATH des hooks assaini) ; le shim `python3.exe` est la vraie correction.

---

## 6. Règle de journalisation (à coller dans le CLAUDE.md du poste)
> À chaque décision / correction / observation / validation significative, journalise immédiatement via la commande auto-suffisante du §4 (PowerShell ou bash selon le shell), puis annonce l'`id`+`source`. Dédup via le MCP (`recall`) avant d'écrire. Ne journalise pas le bavardage.
