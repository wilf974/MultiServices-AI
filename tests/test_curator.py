"""Curation Phase 1 (lecture seule) : detecteurs deterministes, rapport borne, proposals.

Cas calibres sur le REEL observe : correction 'Apache-2.0' journalisee 2x, gabarit
'<sujet>' encore valide (still_standing). La curation OBSERVE et PROPOSE (pending_human),
elle n'ecrit rien ; cloture jamais suppression (C3).

Valide sur COPIE PROPRE (cf. CLAUDE.md).
"""
import copy
from datetime import datetime, timedelta, timezone

from multiservice.curator import (curation_report, find_contradiction_candidates,
                                  find_exact_duplicates, find_near_duplicates,
                                  find_placeholder_facts, find_stale_candidates)
from multiservice.events import AetherEvent, EventType

T0 = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)


def _ev(typ, text, vf, sid="s1", src="project:local", valid_to=None):
    e = AetherEvent(type=typ, title=typ.value, description=text, source=src,
                    observed_at=vf, data={"text": text, "session_id": sid, "turn_id": "t"})
    if valid_to is not None:
        e.valid_to = valid_to
    return e


def test_doublon_exact_reel_correction_apache():
    """Cas reel : la meme correction journalisee 2 fois -> 1 groupe, l'original d'abord."""
    evs = [
        _ev(EventType.CORRECTION, "En fait Apache-2.0", T0, "licence"),
        _ev(EventType.CORRECTION, "En fait Apache-2.0", T0 + timedelta(hours=1), "licence"),
        _ev(EventType.DECISION, "MCP en lecture seule", T0, "constitution"),
    ]
    dups = find_exact_duplicates(evs, as_of=NOW)
    assert len(dups) == 1 and dups[0]["count"] == 2
    assert dups[0]["type"] == "correction"
    d0, d1 = dups[0]["events"]
    assert d0["valid_from"] <= d1["valid_from"]        # le plus ancien = l'original


def test_doublon_exact_respecte_c3():
    """Un doublon deja CLOS (valid_to) ne compte plus : la curation lit la verite courante."""
    evs = [
        _ev(EventType.NOTE, "meme texte", T0),
        _ev(EventType.NOTE, "meme texte", T0 + timedelta(hours=1),
            valid_to=NOW - timedelta(days=1)),         # clos avant as_of
    ]
    assert find_exact_duplicates(evs, as_of=NOW) == []


def test_quasi_doublon_detecte_hors_exact():
    evs = [
        _ev(EventType.NOTE, "le seuil du cache semantique est calibre a 0.95", T0),
        _ev(EventType.NOTE, "le seuil du cache semantique est calibre sur 0.95 reel",
            T0 + timedelta(days=1)),
    ]
    near = find_near_duplicates(evs, threshold=0.6, as_of=NOW)
    assert len(near) == 1 and near[0]["similarity"] >= 0.6
    assert find_exact_duplicates(evs, as_of=NOW) == []  # pas exacts


def test_gabarit_encore_valide_signale():
    """Cas reel : '<sujet>' journalise et toujours debout -> candidat cloture."""
    evs = [
        _ev(EventType.DECISION, "<sujet>", T0, "aetherlife"),
        _ev(EventType.DECISION, "vraie decision redigee", T0, "aetherlife"),
    ]
    hits = find_placeholder_facts(evs, as_of=NOW)
    assert len(hits) == 1 and hits[0]["text"] == "<sujet>"


def test_stale_decision_ancienne_non_corrigee():
    evs = [
        _ev(EventType.DECISION, "vieille decision jamais revisitee", T0, "vieux-sujet"),
        _ev(EventType.DECISION, "decision recente", NOW - timedelta(days=2), "frais"),
    ]
    stale = find_stale_candidates(evs, now=NOW, older_than_days=30)
    assert len(stale) == 1
    assert stale[0]["text"].startswith("vieille") and stale[0]["age_days"] >= 30


def test_stale_exclut_les_decisions_corrigees():
    """Une decision deja corrigee (C3) n'est pas 'stale' : elle a ete revisitee."""
    evs = [
        _ev(EventType.DECISION, "decision revisee depuis", T0, "sujet-vivant"),
        _ev(EventType.CORRECTION, "revirement", T0 + timedelta(days=5), "sujet-vivant"),
    ]
    assert find_stale_candidates(evs, now=NOW, older_than_days=30) == []


def test_contradiction_candidate_meme_session():
    evs = [
        _ev(EventType.DECISION, "le cache sert les reponses au seuil 0.95", T0, "cache"),
        _ev(EventType.DECISION, "le cache ne sert jamais les reponses au seuil 0.95",
            T0 + timedelta(days=1), "cache"),
        _ev(EventType.DECISION, "sujet sans rapport aucun", T0, "ailleurs"),
    ]
    contra = find_contradiction_candidates(evs, min_overlap=0.5, as_of=NOW)
    assert len(contra) == 1 and contra[0]["session_id"] == "cache"


def test_report_compose_bornes_et_compteurs():
    evs = []
    for i in range(25):                                # 25 groupes de doublons exacts
        for _ in range(2):
            evs.append(_ev(EventType.NOTE, f"texte duplique {i}",
                           T0 + timedelta(minutes=i), f"s{i}"))
    r = curation_report(evs, now=NOW, k=20)
    assert r["counts"]["exact_duplicates"] == 25       # compteur COMPLET
    assert len(r["exact_duplicates"]) == 20            # sortie BORNEE
    assert r["truncated"] is True


def test_proposals_uniquement_pour_l_exact_et_pending_human():
    evs = [
        _ev(EventType.CORRECTION, "En fait Apache-2.0", T0, "licence"),
        _ev(EventType.CORRECTION, "En fait Apache-2.0", T0 + timedelta(hours=1), "licence"),
    ]
    r = curation_report(evs, now=NOW)
    assert r["counts"]["proposals"] == 1
    p = r["proposals"][0]
    assert p["action"] == "close_duplicate" and p["status"] == "pending_human"
    assert p["keep"] not in p["targets"]               # l'original survit
    assert len(p["targets"]) == 1                      # la copie est a clore, pas supprimer


def test_filtre_source_canonique():
    evs = [
        _ev(EventType.NOTE, "pareil", T0, src="project:MultiService-IA"),
        _ev(EventType.NOTE, "pareil", T0, src="project:MultiService-IA"),
        _ev(EventType.NOTE, "pareil", T0, src="project:AetherCore"),
    ]
    dups = find_exact_duplicates(evs, as_of=NOW, source_prefix="project:MultiService-IA")
    assert len(dups) == 1 and dups[0]["count"] == 2    # l'autre projet est exclu


def test_curation_est_pure():
    evs = [
        _ev(EventType.CORRECTION, "En fait Apache-2.0", T0, "licence"),
        _ev(EventType.CORRECTION, "En fait Apache-2.0", T0 + timedelta(hours=1), "licence"),
        _ev(EventType.DECISION, "<sujet>", T0, "aetherlife"),
    ]
    snap = copy.deepcopy([e.model_dump() for e in evs])
    curation_report(evs, now=NOW)
    assert [e.model_dump() for e in evs] == snap       # AUCUNE mutation (lecture seule)


# --- Rapport planifie (lecture seule) : verdict d'attention + rendu markdown ---

def _dup_report():
    evs = [_ev(EventType.DECISION, "meme decision exacte", NOW - timedelta(days=1), "s"),
           _ev(EventType.DECISION, "meme decision exacte", NOW - timedelta(hours=1), "s")]
    return curation_report(evs, now=NOW)


def test_report_needs_attention_vrai_si_action_nette():
    """Action NETTE = doublon exact (proposal prete) ou gabarit non rempli."""
    from multiservice.curator import report_needs_attention
    assert report_needs_attention(_dup_report()) is True
    gab = curation_report([_ev(EventType.DECISION, "<le fait, texte reel>",
                               NOW - timedelta(days=1), "s")], now=NOW)
    assert report_needs_attention(gab) is True


def test_report_needs_attention_faux_si_advisory_ou_propre():
    """Les quasi-doublons / contradictions sont ADVISORY (souvent faux positifs) : pas d'alerte."""
    from multiservice.curator import report_needs_attention
    near = curation_report(
        [_ev(EventType.NOTE, "reindex incremental garde index frais sans etape manuelle tache", NOW - timedelta(days=1), "s"),
         _ev(EventType.NOTE, "reindex incremental garde index frais sans etape manuelle tache horaire", NOW - timedelta(days=1), "s")],
        now=NOW)
    assert near["counts"]["near_duplicates"] >= 1
    assert report_needs_attention(near) is False
    clean = curation_report([_ev(EventType.DECISION, "adopter apache-2.0 pour la licence",
                                 NOW - timedelta(days=2), "s")], now=NOW)
    assert report_needs_attention(clean) is False


def test_format_report_markdown_expose_la_commande_pour_un_doublon():
    from multiservice.curator import format_report_markdown
    md = format_report_markdown(_dup_report())
    assert isinstance(md, str)
    assert "memlog-http" in md and "--closes" in md      # commande prete a coller
    assert "doublons exacts" in md.lower()


def test_format_report_markdown_propre_sans_action():
    from multiservice.curator import format_report_markdown
    clean = curation_report([_ev(EventType.DECISION, "adopter apache-2.0 pour la licence",
                                 NOW - timedelta(days=2), "s")], now=NOW)
    md = format_report_markdown(clean)
    assert "--closes" not in md                          # aucune action a proposer
    assert "rien" in md.lower()
