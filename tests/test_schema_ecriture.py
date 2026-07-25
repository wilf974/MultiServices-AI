"""Ecrire STRUCTURE plutot que narratif — cesser d'encoder de la structure en prose.

Constat vecu (24-25/07/2026) : mes entrees de journal font 1500 a 3000 caracteres de prose. Elles
sont fideles, mais un futur agent doit les RE-PARSER pour en extraire ce qui compte : le fait, la
raison, le piege, la commande, la reference. J'encodais de la structure en texte libre parce que le
format n'offrait rien d'autre.

Quatre champs OPTIONNELS a cote du texte (jamais a la place) :
  rationale  le pourquoi         pitfall  le garde-fou associe
  command    la commande a retenir   refs  commits / fichiers / ids

Contraintes non negociables : le texte reste la verite lisible (un event sans ces champs reste
parfaitement valide, C2/C3 intacts), et rien n'est devine — ce qui n'est pas ecrit n'existe pas.
"""
import pytest

from multiservice import ingest, projlog
from multiservice.events import EventType
from multiservice.journal import read_events


def test_les_champs_structures_atterrissent_dans_l_event(tmp_path):
    jp = tmp_path / "j.jsonl"
    projlog.log(jp, "decision", "index vectoriel binaire", source="project:demo",
                session_id="s",
                rationale="le jsonl pesait 5,4x le float32",
                command="python -m multiservice.index --onnx",
                refs=["e271c3f", "multiservice/vecstore.py"])
    e = read_events(jp)[0]
    assert e.data["rationale"].startswith("le jsonl")
    assert e.data["command"] == "python -m multiservice.index --onnx"
    assert e.data["refs"] == ["e271c3f", "multiservice/vecstore.py"]
    assert e.data["text"] == "index vectoriel binaire"      # le texte reste la verite lisible


def test_un_event_sans_champs_structures_reste_valide(tmp_path):
    """RETRO-COMPAT : 2700 events existants n'ont aucun de ces champs."""
    jp = tmp_path / "j.jsonl"
    projlog.log(jp, "note", "un fait tout simple", source="project:demo", session_id="s")
    e = read_events(jp)[0]
    assert e.data["text"] == "un fait tout simple"
    assert "rationale" not in e.data


def test_ingest_accepte_les_champs_structures():
    ok = ingest.valider_champs_structures({"rationale": "parce que", "command": "pytest -q",
                                           "refs": ["abc1234"], "pitfall": "ne pas oublier X"})
    assert ok is None


def test_ingest_refuse_un_champ_du_mauvais_type():
    """Un refus doit enseigner : le message dit QUEL champ et ce qui etait attendu."""
    r = ingest.valider_champs_structures({"refs": "abc1234"})       # chaine au lieu de liste
    assert r is not None and "refs" in r["error"] and "liste" in r["error"]


def test_ingest_refuse_une_commande_absurde():
    """Garde-fou : une « commande » de 5000 caracteres est de la prose deguisee."""
    r = ingest.valider_champs_structures({"command": "x" * 5000})
    assert r is not None and "command" in r["error"]


def test_les_champs_structures_ressortent_au_recall(tmp_path):
    """Ce qu'on ecrit structure doit se relire structure, sinon l'effort est perdu."""
    from multiservice import memory
    jp = tmp_path / "j.jsonl"
    projlog.log(jp, "decision", "index vectoriel binaire", source="project:demo", session_id="s",
                rationale="le jsonl pesait 5,4x le float32",
                command="python -m multiservice.index --onnx")
    hits = memory.recall(read_events(jp), "vectoriel")
    assert hits[0]["rationale"].startswith("le jsonl")
    assert hits[0]["command"] == "python -m multiservice.index --onnx"


def test_pas_de_champ_vide_dans_la_sortie(tmp_path):
    """Economie de sortie : un champ absent ne doit pas encombrer la reponse."""
    from multiservice import memory
    jp = tmp_path / "j.jsonl"
    projlog.log(jp, "note", "sans structure", source="project:demo", session_id="s")
    hits = memory.recall(read_events(jp), "structure")
    assert "rationale" not in hits[0] and "command" not in hits[0]


def test_le_pitfall_associe_est_lisible_dans_resume(tmp_path):
    """Un piege ecrit EN MEME TEMPS que la decision qui l'a revele : c'est la que naissent les
    garde-fous, pas dans une seconde ecriture qu'on oublie de faire."""
    from multiservice import memory
    jp = tmp_path / "j.jsonl"
    projlog.log(jp, "decision", "builder l image mem-ingest", source="project:demo", session_id="s",
                pitfall="builder ne suffit pas : il faut RELANCER le conteneur")
    r = memory.resume(read_events(jp), "project:demo")
    assert any("RELANCER" in (d.get("pitfall") or "") for d in r["etat"]["decisions_valides"])
