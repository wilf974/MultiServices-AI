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

import re
from dataclasses import dataclass
from typing import List, Literal, Tuple

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
    PUR, accent-insensible, conservateur. RETRO-COMPATIBLE (bool).
    Source unique de verite : delegue a classify() (union marqueurs FR + detecteurs regex)."""
    return classify(text).sensitive


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


# =====================================================================================
# API riche (tranche 1 routeur multi-fournisseurs) : verdict a raisons + decision a raison.
# Detecteur = UNION des marqueurs FR (ci-dessus, calibres sur le reel) ET de detecteurs regex
# (secrets/PII). On ne baisse JAMAIS la garde : on ne fait qu'ajouter des signaux. Bord de mot
# partout (pas de match substring naif : "good morning" ne doit pas matcher).
# =====================================================================================

# Detecteurs regex granulaires (raison -> motif). Conservateurs, bornes par \b ou lookbehind.
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_SK = re.compile(r"\bsk-[A-Za-z0-9]{6,}\b")
_PPLX = re.compile(r"\bpplx-[A-Za-z0-9]{6,}\b")
_AKIA = re.compile(r"\bAKIA[0-9A-Z]{8,}\b")
_HEX = re.compile(r"\b[0-9a-fA-F]{32,}\b")          # token/cle haute entropie (hex long)
_LONG_DIGITS = re.compile(r"\b\d{7,}\b")            # tel / carte / id long
# Formats de credential a haute confiance (quasi zero faux positif) : GitHub, Slack, JWT, PEM prive.
_GHP = re.compile(r"\bgh[opsu]_[A-Za-z0-9]{20,}\b")                 # ghp_/gho_/ghs_/ghu_ (GitHub)
_SLACK = re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")           # xoxb-/xoxp-... (Slack)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")  # en-tete base64url
_PEM = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")        # cle privee PEM (pas un cert public)

# (motif, raison) pour les intentions d'attaque. Bornes de mot -> pas de faux positif substring.
_ATTACK: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\bbrute[\s-]?force\b", re.IGNORECASE), "attack:brute_force"),
    (re.compile(r"\bcredential\s+stuffing\b", re.IGNORECASE), "attack:credential_stuffing"),
    (re.compile(r"\bbypass\b", re.IGNORECASE), "attack:bypass"),
    (re.compile(r"\bexploit\b", re.IGNORECASE), "attack:exploit"),
    (re.compile(r"\bexfiltrat(?:e|ion)\b", re.IGNORECASE), "attack:exfiltration"),
]

_REGEX_DETECTORS: List[Tuple[re.Pattern, str]] = [
    (_EMAIL, "pii:email"),
    (_SK, "secret:sk_prefix"),
    (_PPLX, "secret:pplx_prefix"),
    (_AKIA, "secret:akia_prefix"),
    (_HEX, "secret:high_entropy_hex"),
    (_GHP, "secret:github_token"),
    (_SLACK, "secret:slack_token"),
    (_JWT, "secret:jwt"),
    (_PEM, "secret:pem_private_key"),
    (_LONG_DIGITS, "pii:long_digits"),
]


@dataclass(frozen=True)
class SensitivityVerdict:
    sensitive: bool
    reasons: Tuple[str, ...]


@dataclass(frozen=True)
class RoutingDecision:
    route: Literal["local", "cloud"]
    reason: str
    sensitivity: SensitivityVerdict


def classify(text: str) -> SensitivityVerdict:
    """Verdict de sensibilite a RAISONS granulaires. PUR, conservateur, accent-insensible.
    Union : detecteurs regex (secrets/PII/attaque) + marqueurs FR observes (`marker:<m>`)."""
    if not text or not text.strip():
        return SensitivityVerdict(False, ())
    reasons: List[str] = []
    for pat, label in _REGEX_DETECTORS:
        if pat.search(text):
            reasons.append(label)
    for pat, label in _ATTACK:
        if pat.search(text):
            reasons.append(label)
    low = _norm(text)
    for m in SENSITIVE_MARKERS:
        if m in low:
            reasons.append(f"marker:{m}")
    # dedup en preservant l'ordre.
    seen: set = set()
    uniq = tuple(r for r in reasons if not (r in seen or seen.add(r)))
    return SensitivityVerdict(bool(uniq), uniq)


def contains_secret(text: str) -> bool:
    """Vrai si le texte contient un SECRET STRUCTURE a haute confiance (valeur de cle/jeton :
    prefixes sk-/pplx-/AKIA, hex haute entropie). CONSERVATEUR : on ne bloque QUE les valeurs de
    credential reconnaissables — jamais les simples MENTIONS ('token', 'secret', 'mot de passe'),
    ni IP / email / UUID — pour ne pas casser le journal legitime. Sert la garde d'ECRITURE : un
    secret dans un journal append-only est INEFFACABLE (le supersede masque, ne detruit pas). PUR.
    Elargir seulement sur une fuite OBSERVEE au reel (discipline BITS), jamais a l'aveugle."""
    return any(r.startswith("secret:") for r in classify(text).reasons)


def decide(text: str, cloud_ok: bool, has_cloud: bool) -> RoutingDecision:
    """Decision de routage PURE. Regle verrouillee :
    default local ; cloud SEULEMENT si cloud_ok ET has_cloud ET non sensible ; dans le doute -> local."""
    verdict = classify(text)
    if not text or not text.strip():
        return RoutingDecision("local", "empty_input", verdict)
    if verdict.sensitive:
        return RoutingDecision("local", "sensitive_input", verdict)
    if not cloud_ok:
        return RoutingDecision("local", "cloud_not_authorized", verdict)
    if not has_cloud:
        return RoutingDecision("local", "no_cloud_backend", verdict)
    return RoutingDecision("cloud", "cloud_authorized_and_clean", verdict)
