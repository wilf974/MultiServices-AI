"""Ergonomie AGENT — pouvoir lire un souvenir EN ENTIER sans partir a la peche.

Constat vecu le 24/07/2026 : pour lire UNE decision en entier, il fallait enchainer
`recall` -> `replay_event`... et le texte etait encore coupe a 300 caracteres. Neuf coupes en dur
(`[:200]`, `[:300]`, `[:500]`) rendaient la memoire consultable mais pas LISIBLE.

Contrat : `chars=None` (defaut) garde le comportement historique — les sorties restent bornees,
l'economie de sortie est une decision de conception, pas un accident. `chars=0` rend le texte
INTEGRAL ; `chars=N` coupe a N. La coupe reste signalee par le suffixe habituel.
"""
from datetime import datetime, timedelta, timezone

from multiservice import memory
from multiservice.events import AetherEvent, EventType

T0 = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
LONG = "decision tres detaillee. " * 60          # ~1500 caracteres


def _ev(typ, texte, minute=0, sid="s1", tid="t1", src="project:demo"):
    return AetherEvent(type=typ, title=typ.value, description=texte, source=src,
                       observed_at=T0 + timedelta(minutes=minute),
                       data={"text": texte, "session_id": sid, "turn_id": tid})


def test_defaut_inchange_les_sorties_restent_bornees():
    """RETRO-COMPAT : sans rien demander, on garde l'economie de sortie d'origine."""
    evs = [_ev(EventType.DECISION, LONG)]
    d = memory.replay_session(evs, "s1")[0]
    assert len(d["text"]) <= 320 and d["text"] != LONG


def test_chars_zero_rend_le_texte_integral():
    evs = [_ev(EventType.DECISION, LONG)]
    d = memory.replay_session(evs, "s1", chars=0)[0]
    assert d["text"] == LONG


def test_chars_n_coupe_a_n():
    evs = [_ev(EventType.DECISION, LONG)]
    d = memory.replay_session(evs, "s1", chars=50)[0]
    assert d["text"].startswith(LONG[:50]) and len(d["text"]) <= 55


def test_why_rend_le_texte_integral():
    """`why` est l'outil du « pourquoi » : le tronquer, c'est amputer la reponse."""
    evs = [_ev(EventType.COMPLETION, LONG)]
    assert memory.why(evs, "t1", chars=0)[0]["text"] == LONG


def test_lessons_rend_lecon_et_fait_perime_integraux():
    """Une lecon coupee au milieu perd justement ce qu'on venait chercher."""
    evs = [_ev(EventType.DECISION, LONG, 0),
           _ev(EventType.CORRECTION, "en fait non : " + LONG, 1)]
    out = memory.lessons_learned(evs, chars=0)
    lecon = out["lessons"][0]
    assert lecon["correction"] == "en fait non : " + LONG
    assert lecon["superseded"][0]["text"] == LONG


def test_project_review_rend_les_textes_integraux():
    evs = [_ev(EventType.DECISION, LONG)]
    r = memory.project_review(evs, "project:demo", now=T0 + timedelta(days=1), chars=0)
    assert r["decisions_valides"][0]["text"] == LONG


def test_reasoning_rend_les_textes_integraux():
    evs = [_ev(EventType.DECISION, LONG)]
    r = memory.reasoning_chain(evs, "s1", chars=0)
    assert any(s.get("text") == LONG for s in r["steps"])


def test_replay_event_rend_les_textes_integraux():
    evs = [_ev(EventType.DECISION, LONG)]
    r = memory.replay_event(evs, evs[0].id, chars=0)
    assert r["focus"]["text"] == LONG


# --- le parametre doit traverser le chemin SQL, pas seulement le pur ---

def test_chars_traverse_le_chemin_sql(tmp_path):
    """Le serveur route vers SQL : si `chars` s'y perdait, l'option ne servirait a rien en prod."""
    from multiservice import projection
    from multiservice.journal import append_events
    jp = tmp_path / "j.jsonl"
    evs = [_ev(EventType.DECISION, LONG), _ev(EventType.COMPLETION, LONG, 1)]
    append_events(jp, evs)
    p = projection.Projection(tmp_path / "p.db")
    p.update(jp)

    assert projection.why_sql(p, "t1", chars=0)[0]["text"] == LONG
    assert projection.replay_sql(p, "s1", digest=False, chars=0)[0]["text"] == LONG
    assert projection.replay_event_sql(p, evs[0].id, chars=0)["focus"]["text"] == LONG
    assert projection.reasoning_sql(p, "s1", chars=0)["steps"][0]["text"] == LONG
    # et le defaut reste borne
    assert len(projection.why_sql(p, "t1")[0]["text"]) <= 500
