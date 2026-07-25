"""V5 — MANIFESTE D'USAGE : rendre n'importe quelle IA immediatement competente.

La surface est deja ouverte (18 outils MCP, une API web). Ce qui manque pour « utile a TOUTE
IA », c'est un document que l'agent lit EN PREMIER : comment lire, comment ecrire, quoi ne
jamais ecrire, et quelles regles s'imposent a lui. Aujourd'hui cela vit dans `CLAUDE.md` —
specifique a un seul agent, invisible pour ChatGPT ou Ollama.

DEUX exigences non negociables, apprises aujourd'hui a nos depens :

1. **DERIVE, jamais recopie.** Les kinds, les verdicts, les relations sont lus depuis le code.
   Un manifeste redige a la main ment des la premiere evolution — exactement comme les listes de
   types devinees qui ont fait passer des tests pour de mauvaises raisons.
2. **Il ne ment pas sur l'etat.** `health` affichait « available » pendant que le canal
   semantique etait mort. Un manifeste qui promet le semantique quand l'index est vide envoie
   l'agent dans le mur.
"""
from multiservice import manifeste, projlog


def test_liste_les_kinds_REELS():
    """Derive de `projlog.KINDS` : ajouter un kind doit apparaitre sans toucher au manifeste."""
    m = manifeste.rendre()
    for k in projlog.KINDS:
        assert k in m, k


def test_liste_les_verdicts_et_relations_REELS():
    from multiservice.memory import RELATIONS, VERDICTS
    m = manifeste.rendre()
    for mot in list(VERDICTS) + list(RELATIONS):
        assert mot in m, mot


def test_dit_par_ou_commencer():
    """Un agent qui arrive doit savoir quoi appeler en PREMIER."""
    m = manifeste.rendre().lower()
    assert "resume" in m and ("commenc" in m or "premier" in m)


def test_dit_ce_qu_il_ne_faut_JAMAIS_ecrire():
    m = manifeste.rendre().lower()
    assert "secret" in m
    assert "gabarit" in m or "placeholder" in m


def test_porte_les_regles_qui_s_imposent_a_l_agent():
    """C1 l'humain tranche, C2 la source est imposee, C3 on ne supprime jamais."""
    m = manifeste.rendre()
    assert "C1" in m and "C2" in m and "C3" in m


def test_reste_court():
    """Un agent le lit a chaque debut de session : il ne doit pas couter une fortune en contexte."""
    m = manifeste.rendre()
    assert len(m) < 6000, "manifeste trop long : %d caracteres" % len(m)


def test_annonce_l_etat_degrade_quand_on_le_lui_donne():
    """Ne jamais promettre une capacite qui ne repond pas (lecon du 24/07 : health disait
    « available » pendant que le canal semantique etait mort)."""
    m = manifeste.rendre(sante={"degraded": True,
                                "warnings": ["index semantique VIDE (0/2518)"]})
    assert "index semantique VIDE" in m


def test_muet_sur_l_etat_quand_tout_va_bien():
    m = manifeste.rendre(sante={"degraded": False, "warnings": []})
    assert "DEGRAD" not in m.upper()


def test_sans_etat_le_manifeste_reste_valide():
    """RETRO-COMPAT : un appelant qui ne fournit pas la sante obtient quand meme le mode d'emploi."""
    assert len(manifeste.rendre()) > 500


def test_est_du_texte_pur_lisible_par_n_importe_quel_agent():
    """Pas de JSON, pas de balises : un LLM le lit tel quel, quel que soit son harnais."""
    m = manifeste.rendre()
    assert not m.strip().startswith("{") and "<html" not in m.lower()
