"""Comparateur LLM local (curation) : juge des paires de faits, propose consolidations.

FakeBackend a verdict canned (ni reseau, ni modele). Le LLM PROPOSE (pending_human),
n'ecrit rien, cite ses preuves ; JSON illisible -> uncertain (revue humaine, jamais de
proposition a l'aveugle).
"""
import json
from datetime import datetime, timezone, timedelta

from multiservice import comparator
from multiservice.backends import Completion
from multiservice.curator import curation_report
from multiservice.events import AetherEvent, EventType

T0 = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)


def _ev(typ, text, vf, sid="s", src="project:maison"):
    return AetherEvent(type=typ, title=typ.value, description=text, source=src,
                       observed_at=vf, data={"text": text, "session_id": sid, "turn_id": "t"})


class FakeBackend:
    model_id = "qwen-local"
    count_source = "local_tokenizer"

    def __init__(self, text):
        self._text = text
        self.seen = []

    def chat(self, messages, on_token=None, tools=None):
        self.seen.append(messages)
        return Completion(self._text, self.model_id, 5, 5)


def _v(relation, keep=None, rationale="raison"):
    d = {"relation": relation, "rationale": rationale}
    if keep:
        d["keep"] = keep
    return json.dumps(d)


def _near_report():
    evs = [_ev(EventType.NOTE, "reindex incremental garde index frais sans etape manuelle tache", T0),
           _ev(EventType.NOTE, "reindex incremental garde index frais sans etape manuelle tache horaire",
               T0 + timedelta(hours=1))]
    return curation_report(evs, now=NOW)


# --- judge_pair ---

def test_judge_pair_equivalent_avec_keep():
    v = comparator.judge_pair(FakeBackend(_v("equivalent", "b")), "x", "y", "note")
    assert v.relation == "equivalent" and v.keep == "b"


def test_judge_pair_different_keep_none():
    v = comparator.judge_pair(FakeBackend(_v("different")), "x", "y", "note")
    assert v.relation == "different" and v.keep is None


def test_judge_pair_json_illisible_devient_uncertain():
    v = comparator.judge_pair(FakeBackend("je pense que oui, peut-etre"), "x", "y", "note")
    assert v.relation == "uncertain"


def test_judge_pair_json_noye_dans_du_texte():
    txt = 'Analyse :\n```json\n{"relation":"contradictory","rationale":"opposes"}\n```\nfin.'
    v = comparator.judge_pair(FakeBackend(txt), "x", "y", "decision")
    assert v.relation == "contradictory"


def test_judge_pair_prompt_contient_les_deux_textes():
    be = FakeBackend(_v("different"))
    comparator.judge_pair(be, "AAA_texte", "BBB_texte", "note")
    blob = json.dumps(be.seen[0])
    assert "AAA_texte" in blob and "BBB_texte" in blob


class FlakyBackend:
    """Echoue les `fail` premiers appels (erreur transitoire), puis renvoie `text`."""
    model_id = "m"

    def __init__(self, fail, text):
        self.calls = 0
        self.fail = fail
        self.text = text

    def chat(self, messages, on_token=None, tools=None):
        self.calls += 1
        if self.calls <= self.fail:
            raise RuntimeError("ollama transitoire")
        return Completion(self.text, self.model_id, 1, 1)


def test_judge_pair_retente_sur_erreur_transitoire():
    be = FlakyBackend(1, _v("equivalent", "a"))       # echoue 1x puis OK
    v = comparator.judge_pair(be, "x", "y", "note")
    assert v.relation == "equivalent" and be.calls == 2


def test_judge_pair_abandon_si_backend_echoue_toujours():
    class Always:
        model_id = "m"
        def chat(self, *a, **k):
            raise RuntimeError("down")
    v = comparator.judge_pair(Always(), "x", "y", "note")
    assert v.relation == "uncertain"


# --- review_candidates ---

def test_review_equivalent_produit_une_consolidation():
    rep = _near_report()
    assert rep["counts"]["near_duplicates"] >= 1
    res = comparator.review_candidates(rep, FakeBackend(_v("equivalent", "a")))
    assert len(res["consolidations"]) == 1
    c = res["consolidations"][0]
    assert c["status"] == "pending_human"
    assert "memlog-http" in c["command"] and "--closes" in c["command"]
    assert c["keep_id"] and c["close_ids"] and c["keep_id"] not in c["close_ids"]


def test_review_defaut_plus_ancien_si_keep_absent():
    rep = _near_report()
    res = comparator.review_candidates(rep, FakeBackend(_v("equivalent")))  # pas de keep
    older = min(rep["near_duplicates"][0]["events"], key=lambda e: e["valid_from"])
    assert res["consolidations"][0]["keep_id"] == older["id"]


def test_review_different_est_ecarte():
    res = comparator.review_candidates(_near_report(), FakeBackend(_v("different")))
    assert res["consolidations"] == [] and len(res["dismissed"]) == 1


def test_review_json_illisible_va_en_revue_humaine():
    res = comparator.review_candidates(_near_report(), FakeBackend("bla bla"))
    assert res["consolidations"] == [] and len(res["uncertain"]) == 1


def test_review_contradiction_confirmee():
    evs = [_ev(EventType.DECISION, "le cache sert au seuil 0.95", T0, "cache"),
           _ev(EventType.DECISION, "le cache ne sert jamais au seuil 0.95", T0 + timedelta(days=1), "cache")]
    rep = curation_report(evs, now=NOW)
    assert rep["counts"]["contradiction_candidates"] >= 1
    res = comparator.review_candidates(rep, FakeBackend(_v("contradictory")))
    assert len(res["contradictions"]) >= 1


# --- format ---

def test_format_review_markdown_expose_la_commande():
    res = comparator.review_candidates(_near_report(), FakeBackend(_v("equivalent", "a")))
    md = comparator.format_llm_review_markdown(res)
    assert "memlog-http" in md and "--closes" in md


def test_format_review_markdown_vide_dit_rien():
    res = {"consolidations": [], "contradictions": [], "dismissed": [], "uncertain": [], "model": "m"}
    md = comparator.format_llm_review_markdown(res)
    assert "rien" in md.lower()
