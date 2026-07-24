# Runbook — snapshots chiffrés et clés

Pas à pas des gestes courants **et** d'urgence sur les sauvegardes du journal. À lire quand on a
tout oublié, sous stress, un dimanche soir.

> Le *pourquoi* de chaque choix est dans `docs/DECISIONS.md` (24/07/2026). Ici, seulement le *comment*.

---

## 0. La carte, en trois phrases

| | où | chiffré par | qui peut relire |
|---|---|---|---|
| **Journal-vérité** `journal-llm.jsonl` | poste **et** central | *(rien — en clair)* | tout lecteur |
| **Snapshots du poste** `*.bak-*.enc` | poste | keyring local (slot `snapshots`) | le poste |
| **Snapshots du central** `*.bak-*.enc` | central | **clé publique** X25519 | **le poste seul** |

Le central chiffre ses snapshots **sans pouvoir les relire** : il n'a que la publique. La clé privée
(`keyring/central.priv`) ne quitte jamais le poste. C'est voulu — et ça veut dire qu'une
restauration côté central **passe forcément par le poste** (§3).

**Matériel-clé** (tout dans `~/.aethercore/keyring/`) :
`master.key` (protège les snapshots locaux) · `slots/*.key` · `central.priv` (**ouvre les snapshots
du central**) · `central.pub`.

---

## 1. Où j'en suis ? (aucun risque, lecture seule)

```powershell
# poste — combien en clair, combien chiffrés
python -m multiservice.encrypt_snapshots              # dry-run : liste ce qui est encore en clair
python -m multiservice.encrypt_snapshots --list       # inventaire des chiffrés (sans déchiffrer)
```
```bash
# central
ssh -p <SSH_PORT> <user>@mem.example.com \
  'ls -1 ~/.aethercore/journal-llm.jsonl.bak-* | grep -vc "\.enc$"'   # doit afficher 0
```
Attendu en régime normal : **0 en clair des deux côtés**. Sinon → §2.

---

## 2. Chiffrer ce qui traîne en clair

Normalement inutile : `MSIA_sync_merge` le fait après chaque fusion, des deux côtés.

```powershell
python -m multiservice.encrypt_snapshots --apply                      # poste
```
```bash
# central — la publique suffit, il n'a besoin d'aucun keyring
ssh -p <SSH_PORT> <user>@mem.example.com \
  'cd /home/<user>/mem-mcp-main && nice -n 19 ionice -c3 python3 -m multiservice.encrypt_snapshots \
     --dir ~/.aethercore --apply --pubkey ~/.aethercore/central.pub'
```
`nice`/`ionice` : ce travail n'est **jamais** urgent, le central est chargé.

---

## 3. Restaurer un snapshot

### 3a. Snapshot du **poste**
```powershell
python -m multiservice.encrypt_snapshots --decrypt "$env:USERPROFILE\.aethercore\journal-llm.jsonl.bak-<STAMP>.enc" `
                                         --dest "$env:TEMP\restaure.jsonl"
python -c "from multiservice.journal import read_events; print(len(read_events(r'%TEMP%\restaure.jsonl')), 'events')"
```

### 3b. Snapshot du **central** — le geste qui surprend
Le central **ne peut pas** le faire lui-même (`--decrypt` y répond « clé privée requise »). Il faut
rapatrier le fichier, puis l'ouvrir **sur le poste** :

```powershell
scp -P <SSH_PORT> "<user>@mem.example.com:~/.aethercore/journal-llm.jsonl.bak-<STAMP>.enc" .
python -m multiservice.encrypt_snapshots --decrypt ".\journal-llm.jsonl.bak-<STAMP>.enc" `
        --priv "$env:USERPROFILE\.aethercore\keyring\central.priv" --dest ".\restaure.jsonl"
```

> **Toujours restaurer vers un fichier à part**, jamais par-dessus `journal-llm.jsonl`. Comparer
> d'abord (`read_events`, nombre d'events, dernier `valid_from`), décider ensuite.

---

## 4. Sauvegarder le keyring (à refaire après toute nouvelle clé)

Sans lui, **tous** les snapshots sont perdus — c'est le principe même du wrapped-DEK.

```powershell
python -m multiservice.keyring_backup --out "<CHEMIN_HORS_POSTE>\keyring-<DATE>.bundle"
```
La passphrase est demandée à l'écran (jamais en argument : historique du shell, liste des processus).
Le bundle est chiffré par scrypt → il peut aller **n'importe où** : cloud, mail, disque partagé.

**Notez la passphrase hors machine.** Sans elle, le bundle est un presse-papier.

Une copie brute est déjà maintenue automatiquement sur un disque **distinct** (voir `MSIA_sync_merge`),
mais elle ne protège pas contre la perte du poste (vol, incendie) : le bundle, si.

---

## 5. Sinistre — le keyring a disparu

```powershell
python -m multiservice.keyring_backup --restore "<CHEMIN>\keyring-<DATE>.bundle" `
                                      --dest "$env:USERPROFILE\.aethercore\keyring"
```
Puis **vérifier** en ouvrant un snapshot au hasard (§3a). Restaure `master.key`, les slots **et**
les `*.priv` (donc l'accès aux snapshots du central).

Si le bundle *et* les copies ont disparu : les snapshots chiffrés sont définitivement illisibles.
Le journal-vérité, lui, n'est pas chiffré — il reste lisible (et répliqué par `MSIA_sync_merge`).

---

## 6. Brancher un nouveau nœud distant

```powershell
python -m multiservice.encrypt_snapshots --genkey "$env:USERPROFILE\.aethercore\keyring\<NOEUD>"
scp -P <SSH_PORT> "$env:USERPROFILE\.aethercore\keyring\<NOEUD>.pub" "<user>@<HOTE>:~/.aethercore/"
```
**N'envoyez que le `.pub`.** Le `.priv` reste sur le poste — il est repris par la sauvegarde du
keyring (§4) puisqu'elle couvre les `*.priv`.

---

## 7. Index sémantique du central

Le central **n'indexe jamais** (pas de GPU, charge). Le poste indexe, le central sert.

```powershell
pwsh scripts\refresh_index_vps.ps1          # copie le journal central (lecture seule), delta local, envoi
```
Automatique le dimanche à 03:00 (`MSIA_refresh_index_vps`). Contrôle : `index_status` via MCP →
`covered_pct` doit être à 100.

---

## 8. Quand ça casse — où regarder

| symptôme | fichier |
|---|---|
| la fusion / le chiffrement a échoué | `logs\sync-merge.log` (détaillé) et `logs\sync_merge.task.log` (code retour) |
| l'index dérive | `logs\refresh_index_vps.log` |
| une tâche n'a rien fait | `Get-ScheduledTaskInfo -TaskName MSIA_*` → `LastTaskResult` (0 = OK) |

Les 4 tâches `MSIA_*` tournent **sans fenêtre** (lanceur `scripts\run_hidden.vbs`) : leur seule
trace est le journal. Un log vide veut dire que la tâche n'a pas démarré, pas qu'elle a réussi.

---

## 9. À ne jamais faire

- **Committer le keyring** ou un `.priv`. Ils vivent hors dépôt (`~/.aethercore`), qu'ils y restent.
- **Poser le keyring en clair sur le support qui porte les snapshots** — la serrure à côté de la clé.
  Le *bundle chiffré*, lui, va partout.
- **Envoyer un `.priv` sur un nœud distant.** Toute la propriété recherchée disparaîtrait.
- **Restaurer par-dessus `journal-llm.jsonl`** sans comparer d'abord (§3).
- **Lancer une indexation sur le central.** Le partage des rôles est délibéré (§7).
