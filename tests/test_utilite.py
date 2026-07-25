"""V2 — BOUCLE DE RETROACTION : mesurer ce qui SERT.

Constat (25/07/2026) : aucun signal ne dit quel souvenir a evite une erreur, lequel n'a jamais
ete relu. `usage` mesure des tokens, pas de la valeur. Sans ce retour, la curation DEVINE ce
qu'il faut perimer — et une memoire qui grossit sans savoir ce qui compte devient un cimetiere.

Un retour est un evenement comme un autre (append-only, C3) qui POINTE vers le souvenir servi,
sur le patron deja etabli par `data.closes` :

    data.rates = [ids]   data.verdict = useful | useless | prevented_error

Trois consequences, dans l'ordre de leur importance :
  1. un souvenir qui a EVITE UNE ERREUR ne doit JAMAIS etre propose a la cloture — c'est
     exactement celui qu'on serait tente de perimer, faute de l'avoir vu servir ;
  2. un souvenir jamais utile ET ancien devient un candidat legitime ;
  3. le retour est NON AUTORITAIRE (C1) : il informe la curation, il ne clot rien tout seul.
"""
from datetime import datetime, timedelta, timezone

from multiservice import memory
from multiservice.events import AetherEvent, EventType

# Date PASSEE : un evenement date dans le futur est ecarte par la porte bi-temporelle (C3).
# Piege classique des tests de memoire — il a coute trois echecs le 25/07.
T0 = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)


def _ev(typ, texte, minute=0, src="project:demo", **data_extra):
    data = {"text": texte, "session_id": "s1", "turn_id": "t%d" % minute}
    data.update(data_extra)
    return AetherEvent(type=typ, title=typ.value, description=texte, source=src,
                       observed_at=T0 + timedelta(minutes=minute), data=data)


def _retour(cible_id, verdict, minute=5):
    return _ev(EventType.OBSERVATION, "retour d'usage", minute,
               rates=[cible_id], verdict=verdict)


def test_un_retour_est_compte():
    souvenir = _ev(EventType.DECISION, "index binaire", 0)
    evs = [souvenir, _retour(souvenir.id, "useful")]
    u = memory.utilite(evs)
    assert u[souvenir.id]["useful"] == 1


def test_les_verdicts_sont_distingues():
    s = _ev(EventType.PITFALL, "builder n est pas redeployer", 0)
    evs = [s, _retour(s.id, "useful", 1), _retour(s.id, "prevented_error", 2),
           _retour(s.id, "useless", 3)]
    u = memory.utilite(evs)[s.id]
    assert u["useful"] == 1 and u["prevented_error"] == 1 and u["useless"] == 1


def test_un_souvenir_jamais_servi_n_apparait_pas():
    """Economie de sortie : l'absence de signal n'est pas un signal."""
    s = _ev(EventType.DECISION, "jamais relu", 0)
    assert memory.utilite([s]) == {}


def test_un_retour_peut_viser_plusieurs_souvenirs():
    a = _ev(EventType.DECISION, "a", 0)
    b = _ev(EventType.DECISION, "b", 1)
    r = _ev(EventType.OBSERVATION, "retour", 5, rates=[a.id, b.id], verdict="useful")
    u = memory.utilite([a, b, r])
    assert u[a.id]["useful"] == 1 and u[b.id]["useful"] == 1


def test_un_verdict_inconnu_est_ignore():
    """Ensemble FERME : un verdict libre rendrait l'agregation ininterpretable."""
    s = _ev(EventType.DECISION, "x", 0)
    assert memory.utilite([s, _retour(s.id, "genial")]) == {}


def test_recall_expose_l_utilite():
    """Ce qu'on mesure doit se VOIR, sinon le signal ne sert a personne."""
    s = _ev(EventType.DECISION, "index vectoriel binaire", 0)
    hits = memory.recall([s, _retour(s.id, "prevented_error")], "vectoriel")
    assert hits[0]["utilite"]["prevented_error"] == 1


def test_un_souvenir_sans_retour_n_alourdit_pas_le_recall():
    s = _ev(EventType.DECISION, "index vectoriel binaire", 0)
    assert "utilite" not in memory.recall([s], "vectoriel")[0]


def test_un_souvenir_qui_a_evite_une_erreur_est_protege():
    """LE point de V2. Un garde-fou qui a servi UNE fois vaut d'etre garde : c'est precisement
    celui qu'on periimerait, faute de l'avoir vu agir."""
    s = _ev(EventType.PITFALL, "builder n est pas redeployer", 0)
    evs = [s, _retour(s.id, "prevented_error")]
    assert memory.protege_par_utilite(evs, s.id) is True


def test_un_souvenir_juge_inutile_n_est_pas_protege():
    s = _ev(EventType.DECISION, "x", 0)
    assert memory.protege_par_utilite([s, _retour(s.id, "useless")], s.id) is False


def test_le_retour_reste_non_autoritaire():
    """C1 : un retour informe la curation, il ne clot rien tout seul."""
    s = _ev(EventType.DECISION, "x", 0)
    evs = [s, _retour(s.id, "useless")]
    assert memory.as_of(evs) and any(e.id == s.id for e in memory.as_of(evs))


def test_lecture_seule_ne_mute_pas():
    import copy
    s = _ev(EventType.DECISION, "x", 0)
    evs = [s, _retour(s.id, "useful")]
    snap = copy.deepcopy([e.model_dump() for e in evs])
    memory.utilite(evs)
    assert [e.model_dump() for e in evs] == snap


# --- la boucle se ferme : le signal doit ATTEINDRE la curation, et pouvoir etre ECRIT ---

def test_la_curation_epargne_un_souvenir_qui_a_evite_une_erreur():
    """Sans ce garde-fou, V2 serait decoratif : la curation continuerait de proposer la cloture
    de garde-fous eprouves, simplement parce qu'ils sont anciens."""
    from multiservice import curator
    vieux = T0 - timedelta(days=120)
    # DECISION et non PITFALL : les pieges ne sont pas dans CURATED_TYPES, le test passerait
    # pour une mauvaise raison et la protection resterait non testee (constat 25/07).
    piege = AetherEvent(type=EventType.DECISION, title="decision",
                        description="builder n est pas redeployer", source="project:demo",
                        observed_at=vieux,
                        data={"text": "builder n est pas redeployer", "session_id": "s1"})
    retour = AetherEvent(type=EventType.OBSERVATION, title="observation",
                         description="retour", source="project:demo", observed_at=T0,
                         data={"text": "retour", "session_id": "s2",
                               "rates": [piege.id], "verdict": "prevented_error"})
    r = curator.curation_report([piege, retour], now=T0 + timedelta(days=1))
    stale_ids = {s.get("id") for s in r.get("stale_candidates", [])}
    assert piege.id not in stale_ids


def test_un_vieux_souvenir_sans_retour_reste_candidat():
    """Le garde-fou ne doit pas tout epargner : sans signal, la regle d'age s'applique."""
    from multiservice import curator
    vieux = AetherEvent(type=EventType.DECISION, title="decision", description="jamais relu",
                        source="project:demo", observed_at=T0 - timedelta(days=120),
                        data={"text": "jamais relu", "session_id": "s1"})
    r = curator.curation_report([vieux], now=T0 + timedelta(days=1))
    assert any(s.get("id") == vieux.id for s in r.get("stale_candidates", []))


def test_un_retour_peut_etre_ecrit(tmp_path):
    """Un signal qu'on ne peut pas emettre ne sert a rien (lecon du type PITFALL, 25/07)."""
    from multiservice import projlog
    from multiservice.journal import read_events
    jp = tmp_path / "j.jsonl"
    projlog.log(jp, "observation", "ce piege m a evite une erreur", source="project:demo",
                session_id="s", rates=["id-cible"], verdict="prevented_error")
    e = read_events(jp)[0]
    assert e.data["rates"] == ["id-cible"] and e.data["verdict"] == "prevented_error"


def test_l_ingest_refuse_un_verdict_inconnu():
    from multiservice import ingest
    r = ingest.valider_champs_structures({"rates": ["abc"], "verdict": "genial"})
    assert r is not None and "verdict" in r["error"]


def test_l_ingest_accepte_un_retour_valide():
    from multiservice import ingest
    assert ingest.valider_champs_structures({"rates": ["abc"], "verdict": "useful"}) is None
