"""Integrite : chaine de hachage SHA-256 sur les LIGNES BRUTES du journal (tamper-evident, git-like).
Coeur PUR : une modif/suppression/reordre change la tete a partir de la ligne touchee ; `verify`
contre des sceaux {count, head} localise la falsification. Non-invasif (ne touche pas les events)."""
from multiservice.integrity import running_heads, chain_head, verify


def test_running_heads_deterministe_et_chaine():
    lines = ['{"id": 1}', '{"id": 2}', '{"id": 3}']
    h1 = running_heads(lines)
    assert h1 == running_heads(lines)                      # deterministe
    assert len(h1) == 3 and chain_head(lines) == h1[-1]


def test_modif_change_la_tete_a_partir_de_la_ligne():
    lines = ['{"id": 1}', '{"id": 2}', '{"id": 3}']
    h = running_heads(lines)
    tampered = ['{"id": 1}', '{"id": 9}', '{"id": 3}']     # ligne 2 falsifiee
    ht = running_heads(tampered)
    assert ht[0] == h[0]                                    # avant : identique
    assert ht[1] != h[1] and ht[2] != h[2]                 # a partir de la modif : diverge


def test_verify_ok_et_falsification_detectee():
    lines = ["a", "b", "c", "d"]
    seal = {"count": 4, "head": chain_head(lines)}
    assert verify(lines, [seal])["ok"] is True
    r = verify(["a", "X", "c", "d"], [seal])               # ligne 2 falsifiee
    assert r["ok"] is False and r["broken_at"] == 4


def test_verify_localise_au_premier_sceau_divergent():
    lines = ["a", "b", "c", "d"]
    seals = [{"count": 2, "head": chain_head(lines[:2])},
             {"count": 4, "head": chain_head(lines)}]
    r = verify(["a", "X", "c", "d"], seals)                # tamper ligne 2 -> casse le sceau count=2
    assert r["ok"] is False and r["broken_at"] == 2        # localise au 1er sceau touche


def test_suppression_de_ligne_detectee():
    lines = ["a", "b", "c", "d"]
    seal = {"count": 4, "head": chain_head(lines)}
    r = verify(["a", "b", "c"], [seal])                    # une ligne supprimee -> count < sceau
    assert r["ok"] is False


def test_vide():
    assert chain_head([]) == ""
    assert verify([], [])["ok"] is True
