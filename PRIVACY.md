# Politique de confidentialité — API mémoire MultiService-IA

_Dernière mise à jour : 2026-06-23_

Cette politique couvre l'API REST `https://api-mem.woutils.com` (la « Mémoire »), utilisée par
des assistants IA (Custom GPT, connecteurs, scripts) pour lire et écrire une mémoire personnelle.

## Responsable
Service personnel auto-hébergé. Contact : **devclaude5@divabox.net**.

## Données traitées
- **Contenu que vous envoyez** via `POST /remember` (texte, type, sujet de session).
- **Requêtes de recherche** envoyées via `GET /recall` / `GET /recent`.
- **Métadonnées techniques** minimales attachées à chaque écriture : horodatage, et une
  « source » dérivée **du jeton d'API utilisé** (jamais d'une donnée fournie par le client).

L'API ne collecte pas de données de localisation, ni de profil publicitaire, ni de cookies.

## Finalité & base
Mémoriser, restituer et expliquer des notes/décisions personnelles à la demande de l'utilisateur
authentifié. Aucun traitement à d'autres fins.

## Authentification & accès
Accès strictement par **jeton porteur (Bearer)** propre à chaque client. Un jeton inconnu ou
absent est refusé (HTTP 401). Les jetons sont révocables à tout moment (retrait du registre serveur).

## Stockage & conservation
- Stockage **sur un serveur privé** (VPS auto-hébergé), dans un journal append-only.
- Modèle **bi-temporel** : les entrées ne sont pas supprimées mais peuvent être marquées comme
  périmées (corrections horodatées). Suppression définitive sur demande au contact ci-dessus.

## Partage avec des tiers
**Aucune vente, aucun partage** des données à des tiers. Les données ne quittent pas
l'infrastructure du responsable, hormis la réponse renvoyée au client appelant authentifié.
Le transport est chiffré (HTTPS/TLS).

## Vos droits
Accès, rectification, suppression : écrire à **devclaude5@divabox.net**.

## Sécurité
HTTPS obligatoire, authentification par jeton, limitation de débit, isolement des secrets côté
serveur. Aucun système n'étant infaillible, l'utilisateur veille à garder son jeton confidentiel.
