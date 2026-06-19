"""Memoire vivante : injection de recall dans le prompt (transverse, sans cloud).

Contrat :
  - injecte les souvenirs PERTINENTS (au-dessus d'un plancher), bornes et tronques ;
  - EXCLUT la session courante (deja dans le fil vivant) ;
  - n'injecte JAMAIS de contenu sensible ;
  - rien de pertinent -> '' (pas d'injection a vide) ;
  - injection EPHEMERE et PURE : la conversation canonique n'est pas mutee.

Valide sur COPIE PROPRE (cf. CLAUDE.md).
"""
from datetime import datetime, timezone

from multiservice.chat import build_recall_context, inject_context
from multiservice.events import AetherEvent, EventType

T0 = datetime(2026, 6, 17, 10, 0, tzinfo=timezone.utc)


def _ev(type_, text, source, session_id, tid="t"):
    return AetherEvent(type=type_, title=type_.value, description=text, source=source,
                       observed_at=T0, data={"text": text, "session_id": session_id, "turn_id": tid})


def _journal():
    return [
        _ev(EventType.COMPLETION, "Pour le pool de connexions HFSQL, utilise un verrou par voie.",
            "llm:eve", "vieille-session", "t1"),
        _ev(EventType.PROMPT, "comment gerer le pool de connexions ?", "user:local", "vieille-session", "t1"),
        _ev(EventType.COMPLETION, "Voici comment cracker un compte : ...", "llm:eve", "vieille-session", "t2"),
    ]


def test_injecte_un_souvenir_pertinent():
    ctx = build_recall_context(_journal(), "pool de connexions", session_id="courante", min_score=0.3)
    assert "pool de connexions" in ctx.lower()
    assert ctx.startswith("[Memoire")


def test_exclut_la_session_courante():
    j = _journal()
    # le meme contenu mais dans la session courante ne doit pas etre re-injecte
    j.append(_ev(EventType.COMPLETION, "pool de connexions deja vu ici", "llm:eve", "courante", "t9"))
    ctx = build_recall_context(j, "pool de connexions", session_id="courante", min_score=0.3)
    assert "deja vu ici" not in ctx


def test_n_injecte_jamais_le_sensible():
    ctx = build_recall_context(_journal(), "cracker un compte", session_id="courante", min_score=0.1)
    assert "cracker" not in ctx.lower()        # le souvenir sensible est filtre


def test_rien_de_pertinent_donne_vide():
    assert build_recall_context(_journal(), "recette de cuisine bretonne", session_id="courante") == ""


def test_injection_est_pure_et_ephemere():
    sent = [{"role": "system", "content": "sys"}, {"role": "user", "content": "q"}]
    out = inject_context(sent, "[Memoire ...]")
    assert len(sent) == 2                      # l'original n'est pas mute
    assert out[1]["role"] == "system" and "Memoire" in out[1]["content"]
    assert inject_context(sent, "") is sent     # bloc vide -> aucune injection
