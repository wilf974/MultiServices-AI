"""Scaling — les outils ne doivent plus relire le journal ENTIER a chaque appel.

Constat du 24/07/2026 : 11 outils MCP sur 16 appelaient `read_events()` complet. 0,14 s a 2765
events, ~1,5 s a 30k — par appel, et multiplie si le journal est chiffre un jour.

Le remede est deja dans l'architecture : la projection PREFILTRE un sur-ensemble, la fonction PURE
decide de tout. On etend donc le prefiltre a l'acces par session / tour / type / fenetre.

INVARIANT DE TOUS CES TESTS : **ORACLE**. Le resultat servi par SQL doit etre STRICTEMENT egal a
celui de la fonction pure sur le journal complet. Un prefiltre qui change une reponse est un bug,
pas une optimisation.
"""
from datetime import datetime, timedelta, timezone

from multiservice import memory, projection
from multiservice.events import AetherEvent, EventType
from multiservice.journal import append_events, read_events

T0 = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)


def _ev(typ, texte, minute, sid, tid, src="project:demo"):
    return AetherEvent(type=typ, title=typ.value, description=texte, source=src,
                       observed_at=T0 + timedelta(minutes=minute),
                       data={"text": texte, "session_id": sid, "turn_id": tid})


def _journal(tmp_path):
    """Corpus multi-sessions, multi-tours, avec une correction C3."""
    jp = tmp_path / "j.jsonl"
    evs = [
        _ev(EventType.PROMPT, "comment ca marche", 0, "s1", "t1"),
        _ev(EventType.COMPLETION, "voici la reponse", 1, "s1", "t1"),
        _ev(EventType.DECISION, "on part sur le moteur NEMA", 2, "s1", "t2"),
        _ev(EventType.CORRECTION, "en fait un servo", 3, "s1", "t3"),
        _ev(EventType.PROMPT, "autre sujet", 4, "s2", "t4"),
        _ev(EventType.DECISION, "MCP en lecture seule", 5, "s2", "t5"),
        _ev(EventType.VALIDATION, "349 tests verts", 6, "s3", "t6", src="project:autre"),
    ]
    append_events(jp, evs)
    return jp


def _proj(tmp_path, jp):
    p = projection.Projection(tmp_path / "proj.db")
    p.update(jp)
    return p


def test_prefiltre_par_session_est_un_sur_ensemble_exact(tmp_path):
    """Le prefiltre doit rendre TOUS les events de la session, et rien d'autre."""
    jp = _journal(tmp_path)
    p = _proj(tmp_path, jp)
    ids = {e.id for e in p.events_by_session("s1")}
    attendus = {e.id for e in read_events(jp) if e.data.get("session_id") == "s1"}
    assert ids == attendus and len(ids) == 4


def test_prefiltre_par_tour(tmp_path):
    jp = _journal(tmp_path)
    p = _proj(tmp_path, jp)
    ids = {e.id for e in p.events_by_turn("t1")}
    attendus = {e.id for e in read_events(jp) if e.data.get("turn_id") == "t1"}
    assert ids == attendus and len(ids) == 2


def test_oracle_why_sql_egale_pur(tmp_path):
    jp = _journal(tmp_path)
    p = _proj(tmp_path, jp)
    assert projection.why_sql(p, "t1") == memory.why(read_events(jp), "t1")


def test_oracle_replay_sql_egale_pur(tmp_path):
    jp = _journal(tmp_path)
    p = _proj(tmp_path, jp)
    assert projection.replay_sql(p, "s1", digest=False) == \
           memory.replay_session(read_events(jp), "s1")
    assert projection.replay_sql(p, "s1", digest=True) == \
           memory.session_digest(read_events(jp), "s1")


def test_oracle_reasoning_sql_egale_pur(tmp_path):
    jp = _journal(tmp_path)
    p = _proj(tmp_path, jp)
    assert projection.reasoning_sql(p, "s1") == memory.reasoning_chain(read_events(jp), "s1")


def test_oracle_health_sql_egale_pur(tmp_path):
    """`health` n'a besoin d'AUCUN event : ce sont des agregats. Le faire relire 2765 lignes
    pour compter etait le gaspillage le plus net des onze."""
    jp = _journal(tmp_path)
    p = _proj(tmp_path, jp)
    assert projection.health_sql(p) == memory.health(read_events(jp))


def test_session_inconnue_ne_leve_pas(tmp_path):
    jp = _journal(tmp_path)
    p = _proj(tmp_path, jp)
    assert projection.replay_sql(p, "session-qui-n-existe-pas", digest=False) == []
    assert projection.why_sql(p, "tour-inconnu") == []


def test_journal_vide(tmp_path):
    jp = tmp_path / "vide.jsonl"
    jp.write_text("", encoding="utf-8")
    p = _proj(tmp_path, jp)
    assert projection.health_sql(p) == memory.health([])
    assert projection.why_sql(p, "t1") == []


# --- groupe 2 : prefiltre par TYPE et par FENETRE (meme invariant d'oracle) ---

def test_prefiltre_par_types(tmp_path):
    jp = _journal(tmp_path)
    p = _proj(tmp_path, jp)
    ids = {e.id for e in p.events_by_types(["decision", "correction"])}
    attendus = {e.id for e in read_events(jp)
                if e.type.value in ("decision", "correction")}
    assert ids == attendus and len(ids) == 3


def test_oracle_lessons_sql_egale_pur(tmp_path):
    """`lessons` ne lit que corrections + decisions : le reste du journal est du poids mort."""
    jp = _journal(tmp_path)
    p = _proj(tmp_path, jp)
    assert projection.lessons_sql(p) == memory.lessons_learned(read_events(jp))
    assert projection.lessons_sql(p, source_prefix="project:demo") == \
           memory.lessons_learned(read_events(jp), source_prefix="project:demo")


def test_oracle_curation_sql_egale_pur(tmp_path):
    from multiservice import curator
    jp = _journal(tmp_path)
    p = _proj(tmp_path, jp)
    now = T0 + timedelta(days=1)             # instant FIXE : `as_of` est horodate a now()
    assert projection.curation_sql(p, now=now) == curator.curation_report(read_events(jp), now=now)


def test_oracle_project_review_sql_egale_pur(tmp_path):
    jp = _journal(tmp_path)
    p = _proj(tmp_path, jp)
    now = T0 + timedelta(days=1)
    assert projection.project_review_sql(p, "project:demo", now=now) == \
           memory.project_review(read_events(jp), "project:demo", now=now)


def test_oracle_usage_sql_egale_pur(tmp_path):
    """`usage` ne regarde QUE les TOKEN_USAGE : ici aucun, donc l'oracle porte sur le vide."""
    jp = _journal(tmp_path)
    p = _proj(tmp_path, jp)
    assert projection.usage_sql(p) == memory.reuse_stats(read_events(jp))


def test_oracle_replay_event_sql_egale_pur(tmp_path):
    """La chaine causale remonte la SESSION de l'event focus : deux requetes ciblees suffisent."""
    jp = _journal(tmp_path)
    p = _proj(tmp_path, jp)
    cible = [e for e in read_events(jp) if e.description.startswith("on part")][0]
    assert projection.replay_event_sql(p, cible.id) == \
           memory.replay_event(read_events(jp), cible.id)


def test_replay_event_inconnu_ne_leve_pas(tmp_path):
    jp = _journal(tmp_path)
    p = _proj(tmp_path, jp)
    assert projection.replay_event_sql(p, "id-inexistant") == \
           memory.replay_event(read_events(jp), "id-inexistant")


def test_oracle_index_status_sql_egale_pur(tmp_path):
    """`index_status` ne compte que les types INDEXABLES : inutile de relire le reste."""
    jp = _journal(tmp_path)
    p = _proj(tmp_path, jp)
    vecs = {}                                     # index vide : cas le plus frequent au demarrage
    assert projection.index_status_sql(p, vecs) == \
           memory.index_coverage(read_events(jp), vecs)


def test_oracle_briefing_today_sql_egale_pur(tmp_path):
    """`briefing_today` ne regarde qu'une JOURNEE : la fenetre est le prefiltre naturel."""
    jp = _journal(tmp_path)
    p = _proj(tmp_path, jp)
    now = T0 + timedelta(hours=2)
    assert projection.briefing_today_sql(p, now=now) == \
           memory.briefing_today(read_events(jp), now=now)


def test_oracle_project_review_avec_fenetre(tmp_path):
    """Avec `days`, la fenetre temporelle est le vrai discriminant : le pur coupe d'abord sur
    valid_from, donc prefiltrer dessus reste EXACT — et evite de charger tout l'historique."""
    jp = _journal(tmp_path)
    p = _proj(tmp_path, jp)
    now = T0 + timedelta(days=10)
    for jours in (1, 30):
        assert projection.project_review_sql(p, "project:demo", days=jours, now=now) == \
               memory.project_review(read_events(jp), "project:demo", days=jours, now=now), jours


def test_fenetre_ne_perd_pas_un_fait_du_bord(tmp_path):
    """Garde-fou : un fait pile sur la borne doit rester dans la vue (>= cutoff, comme le pur)."""
    jp = _journal(tmp_path)
    p = _proj(tmp_path, jp)
    now = T0 + timedelta(minutes=6)               # le dernier event est a T0+6min
    assert projection.project_review_sql(p, "project:autre", days=1, now=now) == \
           memory.project_review(read_events(jp), "project:autre", days=1, now=now)
