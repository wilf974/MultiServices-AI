"""V4 — CONTRAT DE SESSION : ce qu'il faut retenir, et ce qui attend une decision.

A l'ouverture, `resume` dit les cinq choses a savoir. A la CLOTURE, il manquait le pendant :
« qu'as-tu appris ? » et « qu'est-ce qui attend ton arbitrage ? ». Un agent laisse libre ecrit
trop, ou oublie — constat direct : mes entrees du 24/07 sont des paves, celles du 25/07 (question
posee, schema structure) sont exploitables.

Le second volet repond a une proposition de Wilfred (25/07) : que l'agent PRESENTE les validations
en attente et execute la decision humaine. C1 n'est pas contourne — il est enfin APPLICABLE : un
arbitrage qu'on ne presente jamais n'est pas un arbitrage, c'est un blocage.

Le risque n'est pas que l'agent decide, c'est l'APPROBATION EN LOT : presenter 43 propositions et
obtenir un « ok » respecte C1 dans la forme et le vide dans les faits. D'ou trois garde-fous
testes ici : peu a la fois, le contenu EXACT de ce qui sera clos, et la REVERSIBILITE affichee.
"""
from datetime import datetime, timedelta, timezone

from multiservice import memory
from multiservice.events import AetherEvent, EventType

T0 = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)


def _ev(typ, texte, minute=0, src="project:demo", **data_extra):
    data = {"text": texte, "session_id": "s1", "turn_id": "t%d" % minute}
    data.update(data_extra)
    return AetherEvent(type=typ, title=typ.value, description=texte, source=src,
                       observed_at=T0 + timedelta(minutes=minute), data=data)


def _curation(n=1):
    return {"as_of": T0.isoformat(), "counts": {"proposals": n},
            "proposals": [{"action": "close_duplicate", "targets": ["id-%d" % i],
                           "keep": "id-orig", "rationale": "deux fois le meme fait",
                           "command": 'memlog-http "..." --closes id-%d' % i}
                          for i in range(n)]}


def test_demande_ce_qu_il_faut_retenir():
    """Un agent a qui l'on demande « qu'as-tu appris ? » ecrit mieux qu'un agent laisse libre."""
    c = memory.contrat_cloture([_ev(EventType.DECISION, "un fait")], "project:demo", now=T0)
    assert c["questions"] and any("appris" in q.lower() or "retenir" in q.lower()
                                  for q in c["questions"])


def test_rappelle_d_ecrire_les_pieges():
    """Les pieges sont ce qui a le plus servi : les oublier est le defaut le plus couteux."""
    c = memory.contrat_cloture([], "project:demo", now=T0)
    assert any("piege" in q.lower() for q in c["questions"])


def test_presente_les_validations_en_attente():
    c = memory.contrat_cloture([], "project:demo", now=T0, curation=_curation(1))
    assert len(c["a_decider"]) == 1
    assert c["a_decider"][0]["command"].startswith("memlog-http")


def test_ne_presente_jamais_la_file_entiere():
    """GARDE-FOU n.1 contre l'approbation en lot : 43 propositions d'un coup obtiennent un « ok »
    qui ne juge rien. On en montre peu, on y revient."""
    c = memory.contrat_cloture([], "project:demo", now=T0, curation=_curation(43), k=3)
    assert len(c["a_decider"]) == 3
    assert c["counts"]["a_decider"] == 43            # le compteur reste HONNETE
    assert c["truncated"] is True


def test_affiche_la_reversibilite():
    """GARDE-FOU n.3 : une cloture C3 se clot a son tour — rien n'est detruit. Le dire change le
    niveau de risque acceptable pour l'humain qui tranche."""
    c = memory.contrat_cloture([], "project:demo", now=T0, curation=_curation(1))
    assert c["a_decider"][0]["reversible"] is True


def test_presente_aussi_les_desaccords_entre_agents():
    fait = _ev(EventType.DECISION, "bge-m3 est indispensable", 0)
    contre = _ev(EventType.OBSERVATION, "mesure inverse", 1, src="project:chatgpt",
                 contradicts=[fait.id])
    c = memory.contrat_cloture([fait, contre], "project:demo", now=T0 + timedelta(days=1))
    assert any(d["type"] == "contradiction" for d in c["a_decider"])


def test_rien_a_decider_ne_fait_pas_de_bruit():
    c = memory.contrat_cloture([_ev(EventType.DECISION, "un fait")], "project:demo", now=T0)
    assert c["a_decider"] == [] and c["counts"]["a_decider"] == 0


def test_l_agent_ne_decide_rien_lui_meme():
    """C1 : la sortie ne contient QUE des propositions et leurs commandes. Aucune n'est marquee
    comme appliquee — l'agent presente, l'humain tranche, puis l'agent execute."""
    c = memory.contrat_cloture([], "project:demo", now=T0, curation=_curation(2))
    for d in c["a_decider"]:
        assert d.get("applique") is not True
        assert "command" in d                        # la decision est PRETE, pas prise


def test_lecture_seule_ne_mute_pas():
    import copy
    evs = [_ev(EventType.DECISION, "un fait")]
    snap = copy.deepcopy([e.model_dump() for e in evs])
    memory.contrat_cloture(evs, "project:demo", now=T0, curation=_curation(1))
    assert [e.model_dump() for e in evs] == snap
