"""Normalisation des sources : registre d'alias NON DESTRUCTIF (gouvernance de la cle de routage).

Contrat :
  - `canonical(source)` mappe les graphies connues d'un meme projet vers UNE forme canonique
    (minuscules, sans espace) ; laisse INTACT tout ce qui n'est pas une graphie connue
    (prefixe nu 'project', sources de capture user:/llm:/meter, projets deja canoniques).
  - ECRITURE : `projlog.make_event` canonicalise la source a la construction (goulot unique :
    couvre projlog local ET ingest distant). Le journal n'est jamais reecrit (append-only intact).
  - LECTURE : `recall(source_prefix=...)` reconcilie les graphies -> un filtre sur la forme
    canonique retrouve les evenements ecrits sous l'ancienne graphie, SANS toucher le journal brut.

Valide sur COPIE PROPRE (cf. CLAUDE.md).
"""
from datetime import datetime, timezone

from multiservice.events import AetherEvent, EventType
from multiservice.journal import append_events, read_events
from multiservice.memory import recall
from multiservice.projlog import log, make_event
from multiservice.source_alias import SOURCE_ALIASES, canonical

T0 = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)


def test_canonical_mappe_les_graphies_connues():
    assert canonical("project:MultiService-IA") == "project:multiservice"
    assert canonical("project:multiservice IA") == "project:multiservice"
    assert canonical("project:AetherCore") == "project:aethercore"
    assert canonical("project:Logos") == "project:logos"


def test_canonical_laisse_intact_le_reste():
    # deja canonique
    assert canonical("project:multiservice") == "project:multiservice"
    assert canonical("project:mw_ia") == "project:mw_ia"
    # prefixe nu (filtre large) : ne doit PAS etre aliase
    assert canonical("project") == "project"
    # sources de la couche de capture : jamais touchees
    assert canonical("user:local") == "user:local"
    assert canonical("llm:eve-qwen3-8b") == "llm:eve-qwen3-8b"
    assert canonical("meter") == "meter"
    # decisions fondatrices : laissees telles quelles (choix produit)
    assert canonical("project:local") == "project:local"
    # logos-staging est un ENV distinct, pas une graphie de logos
    assert canonical("project:logos-staging") == "project:logos-staging"


def test_alias_idempotent():
    for src in SOURCE_ALIASES:
        assert canonical(canonical(src)) == canonical(src)


def test_canonical_entree_vide():
    assert canonical("") == ""
    assert canonical(None) == ""


def test_ecriture_canonicalise_la_source(tmp_path):
    """Goulot unique : make_event nettoie la source -> futures ecritures propres (projlog + ingest)."""
    ev = make_event("decision", "un fait", source="project:MultiService-IA",
                    session_id="s", now=T0)
    assert ev.source == "project:multiservice"          # canonicalise a l'ecriture
    jp = tmp_path / "journal.jsonl"
    log(jp, "note", "autre fait", source="project:AetherCore", session_id="s", now=T0)
    assert read_events(jp)[0].source == "project:aethercore"


def test_lecture_reconcilie_les_graphies_sans_toucher_le_journal(tmp_path):
    """recall(source_prefix=canonique) retrouve les events ecrits sous l'ANCIENNE graphie ;
    le journal brut reste tel qu'ecrit (append-only)."""
    jp = tmp_path / "journal.jsonl"
    # event historique ecrit AVANT le registre, graphie sale, injecte directement (pas via make_event)
    sale = AetherEvent(type=EventType.DECISION, title="decision",
                       description="serveur central en service",
                       source="project:MultiService-IA", observed_at=T0,
                       data={"text": "serveur central en service", "session_id": "central", "turn_id": "t"})
    append_events(jp, [sale])
    evs = read_events(jp)
    # le journal brut n'est PAS modifie : la source sur disque reste l'ancienne graphie
    assert evs[0].source == "project:MultiService-IA"
    # mais un filtre sur la forme CANONIQUE retrouve l'evenement
    hits = recall(evs, "serveur central", source_prefix="project:multiservice")
    assert hits, "le filtre canonique doit retrouver l'event ecrit sous l'ancienne graphie"
    assert hits[0]["id"] == sale.id


def test_lecture_prefixe_large_inchange(tmp_path):
    """Le filtre large 'project' continue de tout prendre, graphies confondues."""
    jp = tmp_path / "journal.jsonl"
    log(jp, "decision", "fait multiservice", source="project:MultiService-IA",
        session_id="a", now=T0)
    log(jp, "decision", "fait aethercore", source="project:AetherCore",
        session_id="b", now=T0)
    hits = recall(read_events(jp), "fait", source_prefix="project")
    assert len(hits) == 2
