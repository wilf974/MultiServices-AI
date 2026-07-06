"""Garde anti-placeholder : ne jamais journaliser un gabarit non rempli.

Calibree sur la pollution OBSERVEE dans le journal reel (01/07/2026) — jamais elargie a
l'aveugle (discipline BITS). Dans le doute on laisse passer : la memoire observe.

Valide sur COPIE PROPRE (cf. CLAUDE.md).
"""
from multiservice.hygiene import looks_like_placeholder


def test_attrape_la_pollution_observee():
    # verbatim du journal reel (01/07/2026)
    assert looks_like_placeholder("<le fait, texte reel>") is True
    assert looks_like_placeholder("H3 : <résultat / décision>") is True
    assert looks_like_placeholder("<résultat / décision>") is True
    # gabarit du runbook colle tel quel
    assert looks_like_placeholder('memlog-http "<FAIT>" --kind decision') is True
    assert looks_like_placeholder("<sujet-stable>") is True


def test_texte_vide_est_placeholder():
    assert looks_like_placeholder("") is True
    assert looks_like_placeholder("   ") is True
    assert looks_like_placeholder(None) is True


def test_laisse_passer_les_vrais_textes():
    assert looks_like_placeholder("Adopter Apache-2.0 pour la licence (brevet explicite)") is False
    # humain qui teste != gabarit non rempli (observe au journal, ne doit PAS etre bloque)
    assert looks_like_placeholder("ma premiere decision depuis le bureau") is False


def test_dans_le_doute_on_laisse_passer():
    # segments <...> legitimes : aucun vocabulaire de gabarit dedans
    assert looks_like_placeholder("le modele fuit des blocs <think> en anglais") is False
    assert looks_like_placeholder("balise <div> corrigee dans le HTML") is False
    assert looks_like_placeholder("comparaison : 10 < 20 et 30 > 25") is False


def test_accents_et_casse_reconcilies():
    assert looks_like_placeholder("<Décision>") is True
    assert looks_like_placeholder("<LE TEXTE ICI>") is True
