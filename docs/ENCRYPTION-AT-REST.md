# Chiffrement au repos + crypto-shredding (RGPD art.17) — design durable

> Statut : **plan validé, non implémenté** (P0 à coder). Design issu d'un aller-retour
> Fable 5 (architecte) ↔ Claude (critique + ancrage code), 2026-07-07.
> Respecte les invariants de `CLAUDE.md` : append-only, bi-temporel (C3), provenance (C2),
> lecture pure, souveraineté locale, chaîne de hachage tamper-evident (`integrity.py`).

## 0. Le déblocage conceptuel

`integrity.running_heads` hache **les lignes brutes du disque** (`sha256(tête + "\n" + ligne)`).
Si le contenu sensible vit dans `data.enc` (chiffré), la **ligne-sur-disque EST du ciphertext** :

- **Effacer** = détruire une clé **hors-journal**. La ligne ne bouge pas d'un octet → `running_heads`
  inchangé → tous les sceaux antérieurs restent valides → `--verify` ne crie **pas** à la falsification.
- **Falsifier** = modifier des octets du journal → tête divergente → `verify()` localise.

⚠️ **Précision (①, à marteler au modèle qui implémente)** : ce n'est **pas** un acquis du code actuel
— aujourd'hui la chaîne scelle le **clair** (title/description sont en clair dans la ligne). La propriété
« scelle le ciphertext » est une **conséquence du design ci-dessous**, à mettre en place.

## 1. Modèle de menace

- **Protège** : vol de disque, fuite de sauvegarde, obligation légale d'effacer un fait/une personne
  tout en gardant append-only + preuve d'intégrité + bi-temporalité.
- **Ne protège pas** : attaquant en session vive avec la clé maître en RAM (hors périmètre « at-rest »). Assumé.

## 2. Schéma de clés — enveloppe KEK-wrappe-DEK, 3 niveaux (décision ③)

DEK **dérivée** de HKDF(master, slot) est **rejetée** : elle soude la DEK au master → rotation master =
tout re-chiffrer. On chiffre le contenu sous une **DEK aléatoire**, puis on **wrappe** la DEK.

```
Contenu  ──AES-GCM(DEK aléatoire, nonce)──►  ct            [dans la LIGNE journal, immuable, scellé]
DEK      ──wrap(KEK_slot)──►  wrapped_dek                  [SIDECAR MUTABLE keyring — voir §7 pour le format]
KEK_slot ──wrap(Master)──►    kek_slot.enc                 [keyring/slots/<h>.key, MUTABLE]
Master                                                     [keyring/master.key, 0600, opt. scrypt/DPAPI]
```

**Invariant critique (Fable, corrige une erreur de la 1re passe)** : `wrapped_dek` vit dans un
**sidecar mutable hors-journal**, JAMAIS dans la ligne. Sinon rotation de slot = réécriture de ligne =
re-chiffrement (le défaut même qu'on fuit). Contre-partie assumée : la ligne seule n'est plus
auto-déchiffrable — le keyring (master + slots + wrapped_dek) est requis (comme il l'était déjà).

Ce que ça débloque :
- **Rotation master** = re-wrap des `kek_slot.enc` (N slots). Keyring seul.
- **Rotation d'un slot** (compromission) = re-wrap des `wrapped_dek` du slot. Keyring seul, **jamais** de
  re-chiffrement du contenu ni de réécriture du journal.
- **Deux granularités d'effacement**, toutes deux destructives et hors-journal :
  - **fin** (un fait) = détruire le `wrapped_dek` de `<event_id>`.
  - **gros** (une source/personne) = détruire `slots/<h>.key`.

**Primitives** : `AESGCM` (ou `ChaCha20Poly1305` si CPU sans AES-NI) ; wrap via RFC 3394
(`aes_key_wrap`) ou `AESGCM(KEK)`. **Une seule dépendance crypto : `cryptography` (PyCA)**, isolée dans
`crypto.py` comme `backends.py` isole l'inférence. **Jamais d'AEAD maison.**

## 3. Enveloppe dans la ligne journal (scellée par la chaîne — AUCUN secret dedans)

```json
"data": {"enc": {
  "v": 1, "alg": "AESGCM", "slot": "<slot_id>",
  "nonce": "<b64 12B>", "ct": "<b64 ct+tag>",
  "aad": ["id","type","source"]
}}
```
`title` et `description` de la ligne = `""`. Le vrai contenu est dans `ct` (= JSON canonique de
`{title, description, data\{sans enc\}}`). Nonce aléatoire 12 B par event.

**AAD = QUE des chaînes** `[id, type, source]` (décision ⑥ — *ne jamais y mettre de `datetime`*). `id`
(uuid unique) lie le ciphertext à l'identité de l'event → **aucun swap d'enveloppe possible** ; `type`+`source`
lient la provenance. **`valid_from` et `valid_to` sont hors AAD** : ils sont déjà protégés par la chaîne de
hachage (toute retouche de la ligne casse `running_heads` → `verify()` la localise), donc rien n'est perdu.

⚠️ **Pourquoi pas de `datetime` dans l'AAD (⑥)** : un `valid_from.isoformat()` recalculé après re-parse
n'est **pas byte-stable** (microsecondes/fuseau) → il produirait des `InvalidTag` sur des events
**légitimes** (fausse alerte d'attaque). On supprime le champ fragile plutôt que de le canonicaliser : la
chaîne le couvre déjà. `test_1` doit utiliser un `valid_from` à microsecondes non-nulles pour mordre toute
régression qui ré-introduirait un `datetime` dans l'AAD.

## 4. Chemin de lecture — `decrypt_or_tombstone` (branché dans `read_events`)

- **Clés présentes** → déchiffre, refusionne `title/description/data` → `AetherEvent` normal. Les fonctions
  pures (recall/replay/embeddings) travaillent sur le clair **en mémoire**. La protection at-rest concerne
  le disque, pas la session légitime.
- **Clé détruite (shred)** → `KeyMissing` → **tombstone** : `title="[effacé]"`,
  `description="[effacé RGPD · slot:<id>]"`, `data={"erased":true,...}`, mais **id/type/source/valid_from/
  valid_to conservés** (chaîne + audit + bi-temporalité intacts). Le fait reste interrogeable *comme effacé*,
  jamais silencieusement absent.
- **Clés présentes mais tag KO** → `IntegrityError` (**attaque**, pas effacement — à distinguer nettement).

## 5. Effacement crash-safe (décision ②) — intent-first / destroy / purge, idempotent

Cause racine du « faux effacement RGPD » : la complétude de conformité = **« la clé n'existe plus »**,
jamais « j'ai journalisé que je l'effaçais ».

```
erase(target):                         # target = slot_id  OU  event_id
  1. append event  erasure {targets:[target], reason, authorized_by, ts}   # WAL : intent durable & tamper-evident, D'ABORD (C1)
  2. destroy_keys(target)              # unlink slot key OU wrapped_dek     — idempotent (missing-ok)
  3. purge_projections(target)         # DÉPLOYER slot -> event_ids, évincer de EMBED_PATH PAR event_id (⑤) — idempotent
```
**Intent d'abord** : détruire la clé avant de journaliser puis crasher → clé absente sans trace →
`verify_keyring` crie « censure » (faux positif). Journaliser l'intent d'abord garantit qu'une clé absente
a toujours une autorisation. Prix : une fenêtre « intent existe mais clé encore là » = **incomplet,
détecté et rejouable** (incomplet-mais-détecté > détruit-sans-trace).

### `verify_keyring` BIDIRECTIONNEL (dans `integrity.py`) — avec correctif ⑤

```python
from collections import defaultdict

def _target_event_ids(target, events_of_slot, needed_ids):
    """Une cible d'effacement -> les event_ids concernés (pour purger l'index vecteur, indexé par event_id)."""
    if target in events_of_slot: return set(events_of_slot[target])   # slot -> ses events
    if target in needed_ids:     return {target}                      # event_id -> lui-même
    return set()

def verify_keyring(events, kr, embed_store):
    enc      = [e for e in events if envelope.is_encrypted(e)]
    slot_of  = {e.id: e.data["enc"]["slot"] for e in enc}
    events_of_slot = defaultdict(set)
    for eid, s in slot_of.items(): events_of_slot[s].add(eid)
    needed_ids   = set(slot_of)
    needed_slots = set(slot_of.values())
    requested    = {t for e in events if e.type == EventType.ERASURE for t in e.data["targets"]}

    # ① censure : matériel disparu ET non couvert par un intent (le slot d'un event compte aussi)
    slot_gone = {s for s in needed_slots if not kr.has_slot(s)}
    dek_gone  = {i for i in needed_ids  if not kr.has_dek(i)}
    unauthorized  = {s for s in slot_gone if s not in requested}
    unauthorized |= {i for i in dek_gone if i not in requested and slot_of.get(i) not in requested}

    # ② incomplet : déclaré effacé mais matériel encore présent
    incomplete  = {t for t in requested if (t in events_of_slot and kr.has_slot(t))
                                         or (t in needed_ids     and kr.has_dek(t))}
    # ②bis fuite-vecteur — CORRECTIF ⑤ : DÉPLOYER slot -> event_ids, tester l'index PAR event_id
    for t in requested:
        if any(embed_store.contains(eid) for eid in _target_event_ids(t, events_of_slot, needed_ids)):
            incomplete.add(t)

    return {"ok": not (unauthorized or incomplete),
            "unauthorized": sorted(unauthorized), "incomplete": sorted(incomplete)}
```
> Sans le correctif ⑤, un effacement **gros** (slot) laisserait les vecteurs de ses events dans l'index sans
> détection (`embed_store.contains(slot_id)` = toujours faux) → ②bis rouvert. On déploie donc `slot → {event_ids}`
> avant de toucher le store vecteur, dans `verify_keyring` **et** dans `erase`.

### Reprise idempotente (au boot / dans `status`)

```python
def erase_resume(events, kr, embed_store):
    ev_of_slot, needed = _events_of_slot(events), _needed_ids(events)
    for t in verify_keyring(events, kr, embed_store)["incomplete"]:
        kr.destroy(t)                                                 # rejoue 2, JAMAIS 1 (intent déjà journalisé)
        for eid in _target_event_ids(t, ev_of_slot, needed):         # rejoue 3 PAR event_id (⑤)
            embed_store.evict(eid)
```
Convergence plutôt qu'atomicité multi-fichiers (impossible) : le système tend vers « tout intent journalisé
⇒ clé absente ⇒ vecteur absent ». **Complétude RGPD = `verify_keyring.ok`**, calculée sur l'état réel des
clés — **pas** la présence de l'event.

## 6. Master : où il vit + mode dégradé (Q4)

- `~/.aethercore/keyring/master.key`, `0600`, opt. enveloppé passphrase (`hashlib.scrypt`, stdlib) ;
  sur Windows, wrapper additionnel DPAPI (`CryptProtectData`) lié à la session.
- **Master perdu** = tout le contenu chiffré devient tombstone, en-têtes clairs préservés, chaîne toujours
  valide. **C'est la propriété de sécurité (panic-wipe gratuit), pas un bug.** Atténuation : sauvegarde
  out-of-band (papier/USB) et/ou escrow (master enveloppé sous une clé de recouvrement type `age`).
  **À documenter noir sur blanc : perdre le master = perdre le clair, définitivement.**

## 7. Format du keyring (mutable, hors-journal, jamais scellé)

```
~/.aethercore/keyring/
  master.key               # 32B aléatoires, opt. scrypt(passphrase) / DPAPI. 0600.
  slots/<h>.key            # h = sha256(slot_id).hex()  ; KEK_slot wrappée sous master : {"v":1,"nonce":b64,"ct":b64}
  wrapped/…                # DEK wrappée sous KEK_slot — derrière l'interface KeyStore (⑦)
```
`slot_id` est **hashé** en nom de fichier (`"source:human:x"` n'est pas un nom sûr).

### ⑦ TRANCHÉ — `wrapped_dek` derrière une interface `KeyStore`

Le stockage des `wrapped_dek` est un **détail de backend** invisible au code P0. `encrypt`/`erase`/
`verify_keyring` ne connaissent que l'interface :

```python
class KeyStore(Protocol):                                    # deux impls interchangeables, choix par config
    def has_dek(self, event_id) -> bool: ...
    def get_dek(self, event_id) -> tuple[bytes, bytes]: ...   # (nonce, wrapped)
    def put_dek(self, event_id, slot_id, nonce, wrapped) -> None: ...
    def destroy_dek(self, event_id) -> None: ...              # IDEMPOTENT, destruction RÉELLE
    def present_deks(self) -> set[str]: ...
```

| Backend | Local perso (défaut, P0) | Échelle (opt-in, seuil ~10k) |
|---|---|---|
| Impl | `FileKeyStore` : `wrapped/<event_id>.dek` | `LogKeyStore` : store log-structuré unique |
| Shred | `unlink` → destruction atomique claire | tombstone + compaction **avec rotation SMK** |
| Destruction réelle | garantie par le FS | garantie par **destruction de l'ancienne SMK** |
| Échelle | ✗ explose en inodes à 100k | ✓ un seul objet à sauvegarder |

**Le mécanisme de destruction à l'échelle — crypto-shredding récursif (décision Fable, retenue) :**
`secure_delete`/VACUUM est **interdit** comme mécanisme de destruction — effacer des octets n'est **jamais
prouvable** contre backups, snapshots FS, wear-leveling SSD. À la place, le `LogKeyStore` est **chiffré au
repos sous une Store Master Key (SMK) rotable** :

- écriture = append `{event_id, slot_id, nonce, wrapped_dek}` (scale : un store, pas 100k inodes) ;
- **shred fin** = ① tombstone `{event_id, erased}` (append atomique, `has_dek` honore le dernier record →
  mort logique immédiate) ② compaction : réécrire le store **en omettant les tombstonés, sous une SMK
  fraîche**, puis **détruire l'ancienne SMK** + `unlink` l'ancien fichier.

Détruire l'ancienne SMK rend **tout l'ancien fichier irrécupérable** (y compris les blobs omis), quels que
soient les octets résiduels ou une copie de sauvegarde du ciphertext. On a réduit « effacer N blobs de façon
prouvable » à « **détruire UNE clé** » — le trick du design, récursé au niveau keyring. La SMK est elle-même
wrappée sous Master dans l'en-tête du store (re-wrappée à chaque compaction) ; sa destruction = `unlink` d'un
petit fichier (le cas où `unlink` est propre).

⚠️ **Compaction crash-safe (addition Claude)** : écrire le nouveau fichier + `fsync`, **swap atomique**, PUIS
détruire l'ancienne SMK. Crash avant swap → l'ancien reste valide, on rejoue. Crash après nouveau fichier
durable mais avant destruction de l'ancienne SMK → le tombstoné reste lisible via l'ancienne SMK jusqu'au
nettoyage → **même convergence que `erase_resume`** (état incomplet détecté et rejoué).

⚠️ **Tension backups (nommée, pas cachée)** : le crypto-shred rend le *live* prouvablement mort ; il n'efface
pas une sauvegarde faite **avant** la rotation SMK **si l'ancienne SMK y est aussi sauvegardée**. Règle :
**ne jamais sauvegarder la SMK courante à côté du store** ; la recouvrabilité du store ne tient qu'à Master.
Backups du store = rétention bornée + cycle de re-chiffrement.

**Rejeté : un DEK par slot** (au lieu d'un par event) — clé partagée ⇒ effacer un event force à re-chiffrer
le contenu des autres (le re-chiffrement banni). **DEK par event, non négociable.**

**Décision P0 (pragmatique — corpus réel ~2k events)** : `FileKeyStore` (fichier-par-event) — simple,
atomique, destruction vérifiable, zéro sur-ingénierie. Bascule `LogKeyStore` par config au-delà du seuil,
**sans toucher aucune des 5 fonctions P0**.

## 8. Migration

- **Forward-only (recommandé)** : le chiffrement s'applique aux **nouveaux** events. L'ancien clair reste,
  la chaîne n'est jamais rebaselinée. Simple, non-cassant.
- **Bulk re-encrypt** (`python -m multiservice.encrypt_migrate`) : relit le clair, assigne les slots
  (défaut slot-par-source), génère secrets, réécrit un nouveau journal chiffré + nouveau genesis + nouveau
  sceau, reconstruit les index. **Rebaseline la chaîne** → opération supervisée unique, tracée par un event
  `migration` + C1. Détruire l'ancien clair selon politique.

## 9. Plan d'implémentation P0

### Découpage (nouveaux fichiers)

```
crypto.py      # SEUL import de `cryptography`. Primitives pures bytes->bytes.
envelope.py    # PUR : plaintext canonique, AAD = [id,type,source] (chaînes seules !), build/parse data.enc
keyring.py     # IO au bord : master, KEK_slot. Matériel DESTRUCTIBLE.
keystore.py    # interface KeyStore + FileKeyStore (P0) ; LogKeyStore (échelle, différé)
encrypt.py     # encrypt_event + CLI migration
erase.py       # erase + erase_resume
# read_events() gagne decrypt_or_tombstone()
# integrity.py gagne verify_keyring()
# events.py : EventType.ERASURE = "erasure" (enum ouvert, non-cassant)
```

### Les 8 tests (TDD — ROUGE d'abord)

| # | Test | Assertion |
|---|---|---|
| 1 | roundtrip | `decrypt(encrypt(e)) == e` sur title/description/data |
| 2 | liaison AAD = attaque, pas tombstone | modifier `source` (clés présentes) → `IntegrityError` |
| 3 | chaîne invariante au shred | sceller ; `erase` → sceaux antérieurs `ok`, tête +1 |
| 4 | shred irréversible | `erase` → `read_events` rend tombstone, en-têtes conservés |
| 5 | censure détectée | détruire clé sans event erasure → `verify_keyring.unauthorized` non vide |
| 6 | fausse conformité + reprise | intent journalisé mais crash avant destroy → `incomplete` ; `erase_resume` → `ok` |
| 7 | purge projection, pas de résurrection | après `erase` : id absent de `EMBED_PATH` ; rebuild → pas de ré-embed (tombstone) |
| 8 | rotation = re-wrap only | `rotate_master` + `rotate_slot` → **aucune ligne réécrite**, contenu toujours lisible |

> Ajouter un **test ⑤** : effacement **gros** (slot) → vecteurs des events du slot détectés par `verify_keyring`.

### Ordre pour le modèle qui implémente

1. `crypto.py` + test unitaire aead/wrap (hors schéma).
2. `envelope.py` (pur, AAD = chaînes seules) + test_1 (valid_from à µs non-nulles), test_2.
3. `keystore.py` (`FileKeyStore`) + `keyring.py` (master/slot + destroy/rotate_*) + test_8.
4. Brancher `decrypt_or_tombstone` dans `read_events` + test_4.
5. `erase.py` + `verify_keyring` (bidirectionnel + correctif ⑤, purge par event_id) + test_3,5,6.
6. Purge index + test_7.
7. CLI `encrypt_migrate` (forward-only par défaut).

### Invariants à coller en tête du prompt du petit modèle

- On chiffre le **contenu**, on hache le **ciphertext-sur-disque**, on n'efface **qu'un secret hors-journal**. La ligne ne bouge jamais.
- `wrapped_dek` vit dans le **sidecar mutable** (`KeyStore`), JAMAIS dans la ligne (sinon rotation slot = re-chiffrement).
- **Complétude RGPD = `verify_keyring.ok`** (bidirectionnel) ; purge d'index **par event_id** — une cible `slot` se **déploie** en ses event_ids avant de toucher le store vecteur (⑤), dans `verify_keyring` ET `erase`.
- **AAD = chaînes seules `[id, type, source]`** ; jamais de `datetime` (⑥) — `valid_from`/`valid_to` sont protégés par la chaîne de hachage.
- `wrapped_dek` derrière `KeyStore` : défaut `FileKeyStore` (fichier-par-event) ; à l'échelle `LogKeyStore` (crypto-shred récursif). **Interdit** : `secure_delete`/VACUUM comme mécanisme de destruction ; jamais WAL pour le keyring (⑦).
- `cryptography` importé **uniquement** dans `crypto.py`.
- Clés manquantes → tombstone ; tag KO clés présentes → `IntegrityError` (attaque).

## Décisions figées (récap)

1. Enveloppe = **wrapped-DEK**, `wrapped_dek` **hors-ligne** (sidecar keyring `KeyStore`), ligne = ciphertext sans secret.
2. Complétude RGPD = `verify_keyring.ok` (bidirectionnel), purge/fuite-vecteur résolue **par event_id** (**correctif ⑤**).
3. `erase` = intent-first / destroy / purge, tout idempotent, `erase_resume` au boot.
4. **AAD = chaînes seules `[id, type, source]`**, jamais de `datetime` (**⑥**) ; `valid_from`/`valid_to` couverts par la chaîne.
5. **Tranché (⑦)** : P0 = `FileKeyStore` (fichier-par-event) ; échelle = `LogKeyStore` (crypto-shred récursif SMK rotable). `secure_delete`/VACUUM **interdit** comme destruction ; jamais WAL pour le keyring.
