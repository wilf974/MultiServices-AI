"""Les DOCUMENTS comme projections de la memoire — une seule ecriture, plusieurs vues.

Constat vecu le 24-25/07/2026 : pour chaque chantier, j'ai ecrit la meme information TROIS fois —
`memlog-http` (le fait), `docs/DECISIONS.md` (la version longue) et le coffre Obsidian (la note).
Trois formats, trois risques de divergence, trois fois le travail. Et ils divergent deja : le
coffre annonce « 92 tests », le journal 629.

C'est exactement la doctrine journal/projection appliquee a la documentation : la memoire est la
SOURCE, le markdown une VUE derivee. Mais avec une nuance decisive — un document contient aussi de
la prose que le journal n'a pas (doctrine, design, arbitrages). On ne regenere donc JAMAIS un
fichier entier : on regenere une SECTION delimitee, comme le fait deja le bloc
`OBSIDIAN+MCP-OBLIGATOIRE` de CLAUDE.md. Les faits sont generes, les essais restent ecrits.
"""
from datetime import datetime, timedelta, timezone

from multiservice import render
from multiservice.events import AetherEvent, EventType

T0 = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)


def _ev(typ, texte, minute=0, src="project:demo", **structure):
    data = {"text": texte, "session_id": "s1", "turn_id": "t%d" % minute}
    data.update({k: v for k, v in structure.items() if v})
    return AetherEvent(type=typ, title=typ.value, description=texte, source=src,
                       observed_at=T0 + timedelta(minutes=minute), data=data)


def test_rend_les_faits_du_projet_en_markdown():
    evs = [_ev(EventType.DECISION, "index vectoriel binaire", 0),
           _ev(EventType.DECISION, "hors sujet", 1, src="project:autre")]
    md = render.render_markdown(evs, "project:demo", now=T0 + timedelta(days=1))
    assert "index vectoriel binaire" in md
    assert "hors sujet" not in md                 # isolation par projet


def test_les_champs_structures_deviennent_du_markdown_lisible():
    """Ce qu'on ecrit structure doit se RENDRE lisible : c'est tout l'interet d'avoir arrete
    d'encoder la structure en prose."""
    evs = [_ev(EventType.DECISION, "index binaire", 0,
               rationale="le jsonl pesait 5,4x le float32",
               pitfall="builder n'est pas redeployer",
               command="python -m multiservice.index --onnx",
               refs=["e271c3f", "multiservice/vecstore.py"])]
    md = render.render_markdown(evs, "project:demo", now=T0 + timedelta(days=1))
    assert "5,4x" in md and "builder n'est pas redeployer" in md
    assert "multiservice.index --onnx" in md and "e271c3f" in md


def test_une_decision_corrigee_est_signalee_pas_effacee():
    """C3 jusque dans le rendu : un document qui tait les revisions ment par omission."""
    d = _ev(EventType.DECISION, "on part sur bge-m3", 0)
    c = _ev(EventType.CORRECTION, "en fait MiniLM suffit", 1)
    c.data["closes"] = [d.id]
    md = render.render_markdown([d, c], "project:demo", now=T0 + timedelta(days=1))
    assert "on part sur bge-m3" in md              # jamais efface (C3)
    # Le rendu est en francais accentue (les .md gardent les accents, cf. CLAUDE.md) : on teste
    # la MARQUE de revision, pas une graphie precise.
    ligne = [l for l in md.splitlines() if "bge-m3" in l or "Décision" in l]
    assert any("révisé" in l or "corrigé" in l for l in md.splitlines()), md[:300]


def test_insere_entre_marqueurs_sans_toucher_au_reste(tmp_path):
    """Le document contient de la prose que le journal n'a pas : on ne regenere qu'une SECTION."""
    f = tmp_path / "DECISIONS.md"
    f.write_text("# Mes decisions\n\nProse ecrite a la main, precieuse.\n\n"
                 f"{render.DEBUT}\nvieux contenu\n{render.FIN}\n\n## Suite ecrite a la main\n",
                 encoding="utf-8")
    evs = [_ev(EventType.DECISION, "un fait journalise", 0)]
    render.ecrire_section(f, evs, "project:demo", now=T0 + timedelta(days=1))
    out = f.read_text(encoding="utf-8")
    assert "Prose ecrite a la main, precieuse." in out
    assert "## Suite ecrite a la main" in out
    assert "vieux contenu" not in out             # la section est REMPLACEE
    assert "un fait journalise" in out


def test_regenerer_deux_fois_donne_le_meme_fichier(tmp_path):
    """Idempotence : sinon chaque generation pollue le diff git et on cesse de l'utiliser."""
    f = tmp_path / "D.md"
    f.write_text(f"# Titre\n\n{render.DEBUT}\n{render.FIN}\n", encoding="utf-8")
    evs = [_ev(EventType.DECISION, "un fait", 0)]
    render.ecrire_section(f, evs, "project:demo", now=T0 + timedelta(days=1))
    a = f.read_text(encoding="utf-8")
    render.ecrire_section(f, evs, "project:demo", now=T0 + timedelta(days=1))
    assert f.read_text(encoding="utf-8") == a


def test_fichier_sans_marqueurs_recoit_la_section_a_la_fin(tmp_path):
    f = tmp_path / "neuf.md"
    f.write_text("# Document existant\n\ndu texte\n", encoding="utf-8")
    render.ecrire_section(f, [_ev(EventType.DECISION, "un fait", 0)], "project:demo",
                          now=T0 + timedelta(days=1))
    out = f.read_text(encoding="utf-8")
    assert "du texte" in out and render.DEBUT in out and "un fait" in out


def test_fichier_inexistant_est_cree(tmp_path):
    f = tmp_path / "sous" / "dossier" / "N.md"
    render.ecrire_section(f, [_ev(EventType.DECISION, "un fait", 0)], "project:demo",
                          now=T0 + timedelta(days=1))
    assert "un fait" in f.read_text(encoding="utf-8")


def test_le_rendu_ne_mute_pas_le_journal():
    import copy
    evs = [_ev(EventType.DECISION, "un fait", 0)]
    snap = copy.deepcopy([e.model_dump() for e in evs])
    render.render_markdown(evs, "project:demo", now=T0 + timedelta(days=1))
    assert [e.model_dump() for e in evs] == snap


def test_projet_sans_fait_rend_une_section_honnete():
    md = render.render_markdown([], "project:vide", now=T0)
    assert "aucun" in md.lower() or "vide" in md.lower()
