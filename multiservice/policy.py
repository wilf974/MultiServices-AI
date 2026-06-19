"""Transverse - Politique de routage multi-fournisseurs (PUR, testable).

Invariant NON NEGOCIABLE (souverainete (c) + securite) :
  **un tour SENSIBLE ne quitte JAMAIS la machine.** Il est servi par le modele LOCAL, point.
On n'autorise le cloud que pour un tour NON sensible ET quand l'appelant l'a explicitement permis.

Regle d'or (heritee du cache, esprit BITS) : DANS LE DOUTE, LOCAL. Tout ce qu'on ne sait pas
classer reste local. La fuite vers un fournisseur hebergé est l'erreur couteuse a eviter ; la
sur-localisation ne coute qu'un peu d'economie. On penche donc toujours vers le local.

`is_sensitive` v1 : marqueurs OBSERVES sur le reel (identifiants/secrets + intention d'acces non
autorise). Accent-insensible (reutilise skills._norm). Conservateur, A CALIBRER sur le reel ;
ne JAMAIS abaisser la garde sans preuve terrain (lecon BITS : calibrer sur l'observe).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .skills import _norm

LOCAL = "local"
CLOUD = "cloud"

# Marqueurs de sensibilite (normalises, sans accents). v1 issu du journal reel + bon sens souverain.
#  - secrets / identifiants / donnees a ne pas exfiltrer vers un cloud,
#  - intention d'acces non autorise (brute force, cracking de comptes) vue dans le journal.
SENSITIVE_MARKERS: List[str] = [
    # secrets & identifiants
    "mot de passe", "motdepasse", "password", "passwd", "identifiant", "credential",
    "cle api", "api key", "api_key", "token", "secret", "clef privee", "private key",
    "ssh key", ".pem", "connexion sql", "chaine de connexion", "dsn",
    # donnees personnelles / confidentielles
    "numero de carte", "carte bancaire", "iban", "rib", "numero de securite sociale",
    # intention d'attaque / acces non autorise (observe sur le reel)
    "brute force", "bruteforce", "force brute", "cracker", "craquer", "crack ",
    "pirater", "piratage", "hack ", "hacker un", "casser le mot de passe",
    "compte facebook", "compte instagram", "acces non autorise", "contourner l'authentification",
]


def is_sensitive(text: str) -> bool:
    """Vrai si le texte doit rester LOCAL (secret/confidentiel OU intention d'acces non autorise).
    PUR, accent-insensible, conservateur. v1 par marqueurs observes."""
    if not text or not text.strip():
        return False
    low = _norm(text)
    return any(m in low for m in SENSITIVE_MARKERS)


@dataclass(frozen=True)
class RouteDecision:
    target: str          # LOCAL | CLOUD
    sensitive: bool
    reason: str


def route(prompt: str, allow_cloud: bool = False,
          cloud_available: bool = False) -> RouteDecision:
    """Choisit le backend d'un tour. PUR. Invariant : sensible -> LOCAL toujours.

    - sensible                      -> LOCAL (jamais de fuite, quoi qu'il arrive),
    - cloud non permis/indisponible -> LOCAL (fail-safe),
    - sinon                         -> CLOUD (l'appelant a explicitement opte).
    """
    if not prompt or not prompt.strip():
        return RouteDecision(LOCAL, False, "entree vide : repli local (dans le doute, local)")
    if is_sensitive(prompt):
        return RouteDecision(LOCAL, True, "contenu sensible : ne quitte jamais la machine")
    if not (allow_cloud and cloud_available):
        return RouteDecision(LOCAL, False, "cloud non permis ou indisponible : repli local (fail-safe)")
    return RouteDecision(CLOUD, False, "tour non sensible, cloud permis et disponible")
