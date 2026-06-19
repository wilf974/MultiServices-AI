"""S16 - cache de resultat : hit/miss, garde C3 (jamais perime), purete structurelle."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from multiservice.backends import Completion
from multiservice.cache import ResultCache, is_valid, request_key
from multiservice.events import AetherEvent, EventType

T0 = datetime(2026, 6, 16, 10, 0, tzinfo=timezone.utc)
MSG = [{"role": "user", "content": "salut"}]


def test_cle_stable_et_sensible_au_contenu():
    assert request_key(MSG) == request_key([{"role": "user", "content": "salut"}])
    assert request_key(MSG) != request_key([{"role": "user", "content": "slt"}])


def test_hit_apres_put(tmp_path):
    c = ResultCache(tmp_path / "cache.jsonl")
    assert c.get(MSG, "s1") is None                       # miss au depart
    c.put(MSG, Completion("Salut !", "qwen3.6", 3, 2), session_id="s1")
    hit = c.get(MSG, "s1")
    assert hit is not None and hit.text == "Salut !"
    assert hit.cached_tokens == 3                          # tout l'input epargne


def test_miss_si_messages_differents(tmp_path):
    c = ResultCache(tmp_path / "cache.jsonl")
    c.put(MSG, Completion("Salut !", "qwen3.6", 3, 2), session_id="s1")
    assert c.get([{"role": "user", "content": "autre"}], "s1") is None


def _correction(session_id, at):
    return AetherEvent(type=EventType.CORRECTION, title="corr", source="user",
                       observed_at=at, data={"session_id": session_id})


def test_garde_c3_correction_invalide_le_cache(tmp_path):
    c = ResultCache(tmp_path / "cache.jsonl")
    c.put(MSG, Completion("Salut !", "qwen3.6", 3, 2), session_id="s1", now=T0)
    # une correction APRES, MEME session -> ne sert plus (jamais perime)
    after = [_correction("s1", T0 + timedelta(minutes=5))]
    assert c.get(MSG, "s1", after) is None
    # une correction dans une AUTRE session -> le hit reste valide
    other = [_correction("s2", T0 + timedelta(minutes=5))]
    assert c.get(MSG, "s1", other) is not None
    # une correction AVANT la mise en cache -> sans effet
    before = [_correction("s1", T0 - timedelta(minutes=5))]
    assert c.get(MSG, "s1", before) is not None


def test_purete_structurelle_aucun_appel_modele():
    src = (Path(__file__).resolve().parents[1] / "multiservice" / "cache.py").read_text(encoding="utf-8")
    for interdit in ("urlopen", "Llama", "create_chat_completion", "subprocess", "os.system"):
        assert interdit not in src, f"cache.py ne doit pas contenir '{interdit}'"
