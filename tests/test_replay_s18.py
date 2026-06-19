"""Sprint 18 - test de regression : replay event -> chaine causale (NEUF, D16/S18).

Contrat grave (feuille de route S18) :
  (a) le replay event-centre NE MUTE RIEN,
  (b) il CITE ses preuves (id, source, dates),
  (c) il resout une vraie chaine antecedents -> tour focus, dans l'ordre,
  (d) id inconnu = reponse sure (found=False), jamais d'exception,
  (e) la bi-temporalite C3 (cloture / correction) est remontee, jamais effacee.

Valide sur COPIE PROPRE (cf. CLAUDE.md : le montage bac-a-sable tronque les editions).
"""
import copy
from datetime import datetime, timedelta, timezone

from multiservice.backends import Completion
from multiservice.events import AetherEvent, EventType
from multiservice.memory import replay_event
from multiservice.router import events_for_turn

T0 = datetime(2026, 6, 18, 9, 0, tzinfo=timezone.utc)
SID = "sess-1"


def _session():
    """3 tours d'affilee dans une meme session, + une correction posterieure."""
    evs = []
    prompts = ["pose le contexte du projet", "quelle est l'archi du cache", "et la garde C3 ?"]
    for i, p in enumerate(prompts):
        t = T0 + timedelta(minutes=10 * i)
        evs += events_for_turn(p, Completion(f"reponse {i}", "eve", 5, 4), "local_tokenizer",
                               session_id=SID, now=t)
    return evs


def _focus_completion(evs):
    """La completion du DERNIER tour = l'evenement dont on veut la chaine causale."""
    comps = [e for e in evs if e.type == EventType.COMPLETION]
    return comps[-1]


def test_replay_ne_mute_rien():
    evs = _session()
    snapshot = copy.deepcopy([e.model_dump() for e in evs])
    focus = _focus_completion(evs)
    replay_event(evs, focus.id, depth=3)
    assert [e.model_dump() for e in evs] == snapshot, "replay doit etre PUR : aucune mutation"


def test_replay_cite_ses_preuves():
    evs = _session()
    focus = _focus_completion(evs)
    out = replay_event(evs, focus.id, depth=3)
    assert out["found"] is True
    assert out["focus"]["id"] == focus.id
    assert out["focus"]["source"] and out["focus"]["valid_from"]
    for turn in out["antecedents"]:
        for ev in turn["events"]:
            assert ev["id"] and ev["source"], "chaque maillon doit porter sa provenance (C2)"


def test_replay_resout_la_chaine_dans_l_ordre():
    evs = _session()
    focus = _focus_completion(evs)
    out = replay_event(evs, focus.id, depth=3)
    # 3 tours au total -> les 3 doivent apparaitre, le focus en dernier.
    starts = [t["valid_from"] for t in out["antecedents"]]
    assert starts == sorted(starts), "antecedents ordonnes du plus ancien au focus"
    assert out["antecedents"][-1]["is_focus_turn"] is True
    assert all(not t["is_focus_turn"] for t in out["antecedents"][:-1])


def test_replay_borne_la_profondeur():
    evs = _session()
    focus = _focus_completion(evs)
    out = replay_event(evs, focus.id, depth=1)
    # depth=1 -> tour focus + 1 antecedent = 2 tours max.
    assert len(out["antecedents"]) == 2


def test_replay_id_inconnu_est_sur():
    out = replay_event(_session(), "id-qui-n-existe-pas")
    assert out["found"] is False
    assert out["antecedents"] == []


def test_replay_remonte_la_cloture_et_la_correction_c3():
    evs = _session()
    focus = _focus_completion(evs)
    # cloture propre du focus (C3 : on borne, on ne supprime pas)
    focus.valid_to = T0 + timedelta(hours=1)
    # une correction posterieure dans la meme session
    corr = AetherEvent(
        type=EventType.CORRECTION, title="correction", description="en fait la garde C3 differe",
        source="user:local", observed_at=T0 + timedelta(minutes=40),
        data={"session_id": SID, "turn_id": "t-corr"},
    )
    out = replay_event(evs + [corr], focus.id, depth=3)
    assert out["bitemporal"]["closed"] is True
    assert out["bitemporal"]["valid_to"] is not None
    assert corr.id in out["bitemporal"]["corrected_by"]
