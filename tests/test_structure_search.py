"""Secondaire — recherche par STRUCTURE dans recall (has_code / has_table).

Contrat : has_code ne garde que les souvenirs avec un bloc ``` ; has_table ceux avec un tableau
markdown (ligne |---|). Teste sur le texte COMPLET. PUR, lecture seule.

Valide sur COPIE PROPRE (cf. CLAUDE.md).
"""
from datetime import datetime, timezone

from multiservice.events import AetherEvent, EventType
from multiservice.memory import _has_code, _has_table, recall

T0 = datetime(2026, 6, 17, 10, 0, tzinfo=timezone.utc)

CODE = "Voici la solution pour odbc :\n```python\nconn = pyodbc.connect(dsn)\n```\nVoila."
TABLE = "Comparatif odbc :\n| Param | Valeur |\n| :--- | :--- |\n| pool | 8 |"
PLAIN = "Reponse odbc en texte simple sans structure particuliere."


def _ev(text):
    return AetherEvent(type=EventType.COMPLETION, title="x", description=text, source="llm:eve",
                       observed_at=T0, data={"text": text, "turn_id": "t", "session_id": "s"})


def test_helpers_detectent_la_structure():
    assert _has_code(CODE) and not _has_code(PLAIN)
    assert _has_table(TABLE) and not _has_table(PLAIN)


def test_recall_has_code_ne_garde_que_le_code():
    r = recall([_ev(CODE), _ev(TABLE), _ev(PLAIN)], "odbc", has_code=True)
    assert len(r) == 1 and "```" in [_ev(CODE)][0].data["text"]   # un seul, celui au code
    assert r[0]["text"]  # extrait non vide


def test_recall_has_table_ne_garde_que_le_tableau():
    r = recall([_ev(CODE), _ev(TABLE), _ev(PLAIN)], "odbc", has_table=True)
    assert len(r) == 1


def test_recall_sans_filtre_garde_tout_le_pertinent():
    r = recall([_ev(CODE), _ev(TABLE), _ev(PLAIN)], "odbc")
    assert len(r) == 3
