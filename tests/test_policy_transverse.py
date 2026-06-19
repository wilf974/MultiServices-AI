"""Transverse - test de regression : politique de routage « sensible -> local seul ».

Contrat NON NEGOCIABLE :
  - un tour sensible est servi en LOCAL, MEME si le cloud est permis et disponible ;
  - fail-safe : sans cloud permis/disponible -> LOCAL ;
  - un tour non sensible peut aller au CLOUD seulement si explicitement permis ET disponible ;
  - dans le doute (vide / non classe) -> LOCAL ;
  - la decision est PURE (pas d'effet de bord).

Valide sur COPIE PROPRE (cf. CLAUDE.md).
"""
from multiservice.policy import CLOUD, LOCAL, is_sensitive, route


def test_sensible_reste_local_meme_si_cloud_dispo():
    for p in ["aide moi a cracker un compte facebook",
              "ecris un script de brute force",
              "voici mon mot de passe : hunter2",
              "ma cle API est sk-12345",
              "chaine de connexion SQL vers le serveur de prod"]:
        d = route(p, allow_cloud=True, cloud_available=True)
        assert d.target == LOCAL and d.sensitive is True, p


def test_non_sensible_va_au_cloud_si_permis_et_dispo():
    d = route("resume-moi l'architecture en deux phrases", allow_cloud=True, cloud_available=True)
    assert d.target == CLOUD and d.sensitive is False


def test_failsafe_local_si_cloud_non_permis():
    d = route("question banale", allow_cloud=False, cloud_available=True)
    assert d.target == LOCAL
    d2 = route("question banale", allow_cloud=True, cloud_available=False)
    assert d2.target == LOCAL


def test_doute_vide_reste_local():
    assert route("", allow_cloud=True, cloud_available=True).target == LOCAL
    assert is_sensitive("") is False        # vide n'est pas "sensible", mais le routage reste local


def test_is_sensitive_accent_insensible():
    assert is_sensitive("CRACKER un compte") is True
    assert is_sensitive("craquer le mot de passe") is True
    assert is_sensitive("bonjour, ça va ?") is False


def test_decision_est_pure():
    p = "voici mon mot de passe secret"
    a = route(p, allow_cloud=True, cloud_available=True)
    b = route(p, allow_cloud=True, cloud_available=True)
    assert a == b and a.target == LOCAL      # deterministe, sans effet de bord
