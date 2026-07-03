"""Phase 2 curation : cloture CIBLEE (data.closes) + file journal-as-queue (data.rejects).

Contrat : une CORRECTION valide portant data.closes=[ids] clot PRECISEMENT ces evenements.
Elle vit dans une session NEUTRE (curation-closures) : aucun effet session+temps sur la
session d'origine — l'original a garder SURVIT (decouverte de design du 02/07). Le journal
EST la file : cloture approuvee -> le doublon sort des rapports suivants ; rejet humain
(data.rejects) -> la proposition ne revient plus en pending. Cloture, JAMAIS suppression.

Valide sur COPIE PROPRE (cf. CLAUDE.md).
"""
from datetime import datetime, timedelta, timezone

from multiservice.curator import (CLOSURE_SESSION, curation_report,
                                  find_exact_duplicates)
from multiservice.events import AetherEvent, EventType
from multiservice.memory import lessons_learned, recall

T0 = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)


def _ev(typ, text, vf, sid="s1", src="project:local", data=None):
    d = {"text": text, "session_id": sid, "turn_id": "t"}
    if data:
        d.update(data)
    return AetherEvent(type=typ, title=typ.value, description=text, source=src,
                       observed_at=vf, data=d)


def _dup_pair():
    a = _ev(EventType.VALIDATION, "hooks repares apres relance", T0, "journalisation")
    b = _ev(EventType.VALIDATION, "hooks repares apres relance",
            T0 + timedelta(minutes=5), "journalisation")
    return a, b


def _closure(targets, vf):
    return _ev(EventType.CORRECTION, "curation approuvee : cloture de doublons", vf,
               CLOSURE_SESSION, data={"closes": list(targets)})


def test_recall_marque_le_clos_superseded():
    a, b = _dup_pair()
    c = _closure([b.id], T0 + timedelta(days=1))
    hits = {h["id"]: h for h in recall([a, b, c], "hooks repares", as_of=NOW)}
    assert hits[b.id]["superseded"] is True
    assert c.id in hits[b.id]["corrected_by"]          # provenance de la cloture (C2)
    assert hits[a.id]["superseded"] is False           # l'original a garder SURVIT


def test_cloture_ciblee_sans_effet_sur_la_session_d_origine():
    """Le piege deniche le 02/07 : une correction DANS la session d'origine aurait perime
    tout l'anterieur, original compris. La session neutre l'evite — preuve."""
    a, b = _dup_pair()
    autre = _ev(EventType.NOTE, "autre fait de la meme session", T0, "journalisation")
    c = _closure([b.id], T0 + timedelta(days=1))
    hits = {h["id"]: h for h in recall([a, b, autre, c], "fait session", as_of=NOW)}
    assert hits[autre.id]["superseded"] is False       # rien d'autre ne bouge


def test_still_standing_exclut_le_clos():
    d1 = _ev(EventType.DECISION, "decision dupliquee", T0, "sujet")
    d2 = _ev(EventType.DECISION, "decision dupliquee", T0 + timedelta(minutes=1), "sujet")
    c = _closure([d2.id], T0 + timedelta(days=1))
    ids = {s["id"] for s in lessons_learned([d1, d2, c])["still_standing"]}
    assert d1.id in ids and d2.id not in ids


def test_le_doublon_disparait_du_rapport_apres_cloture():
    """La boucle se ferme : approuver (= journaliser la cloture) nettoie le rapport suivant."""
    a, b = _dup_pair()
    c = _closure([b.id], T0 + timedelta(days=1))
    assert len(find_exact_duplicates([a, b], as_of=NOW)) == 1      # avant
    assert find_exact_duplicates([a, b, c], as_of=NOW) == []       # apres
    assert curation_report([a, b, c], now=NOW)["counts"]["proposals"] == 0


def test_cloture_bitemporelle():
    """as_of ANTERIEUR a la cloture : le doublon etait encore la (l'histoire reste lisible)."""
    a, b = _dup_pair()
    c = _closure([b.id], T0 + timedelta(days=10))
    assert len(find_exact_duplicates([a, b, c], as_of=T0 + timedelta(days=5))) == 1


def test_rejet_supprime_la_proposition_pas_le_signalement():
    a, b = _dup_pair()
    rej = _ev(EventType.NOTE, "proposition rejetee : doublon volontaire (garder les 2)",
              T0 + timedelta(days=1), "curation-reviews", data={"rejects": [b.id]})
    r = curation_report([a, b, rej], now=NOW)
    assert r["counts"]["exact_duplicates"] == 1        # toujours SIGNALE (la memoire observe)
    assert r["counts"]["proposals"] == 0               # mais plus PROPOSE (l'humain a tranche)
    assert r["counts"]["proposals_rejected"] == 1


def test_proposition_porte_ses_commandes():
    a, b = _dup_pair()
    p = curation_report([a, b], now=NOW)["proposals"][0]
    cmd = p["command"]
    assert cmd.startswith("memlog-http ") and "--kind correction" in cmd
    assert f"--session {CLOSURE_SESSION}" in cmd
    assert cmd.rstrip().endswith(f"--closes {b.id}")   # la copie, jamais l'original
    assert a.id not in cmd.split("--closes")[1]
    assert "--rejects " + b.id in p["command_reject"]  # le rejet aussi, pret a coller
