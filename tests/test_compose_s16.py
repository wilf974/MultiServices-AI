"""S16 etape 2 - cloture C3 cote contexte : fenetre, repere, purete, sans perte."""
from multiservice.compose import compose, dropped_count

SYS = {"role": "system", "content": "sys"}


def _conv(n_pairs):
    msgs = [SYS]
    for i in range(n_pairs):
        msgs.append({"role": "user", "content": f"u{i}"})
        msgs.append({"role": "assistant", "content": f"a{i}"})
    msgs.append({"role": "user", "content": "courant"})   # message courant (demi-tour)
    return msgs


def test_pas_de_cloture_si_court():
    m = _conv(2)                       # 5 msgs de corps <= 2*6+1
    assert compose(m, keep_turns=6) == m


def test_cloture_garde_systeme_et_K_derniers():
    m = _conv(20)                      # corps = 41 msgs
    out = compose(m, keep_turns=3)     # garde 2*3+1 = 7 msgs de corps + repere + systeme
    assert out[0]["role"] == "system" and out[0]["content"] == "sys"
    assert out[1]["role"] == "system" and "clotures" in out[1]["content"]
    body = [x for x in out if not (x["role"] == "system")]
    assert len(body) == 7
    assert body[-1]["content"] == "courant"          # le message courant est garde


def test_dropped_count_coherent():
    m = _conv(20)
    assert dropped_count(m, keep_turns=3) == (41 - 7)


def test_compose_ne_mute_pas_l_entree():
    m = _conv(10)
    before = list(m)
    compose(m, keep_turns=2)
    assert m == before                                # entree intacte (rien perdu cote session)


def test_reduction_reelle():
    m = _conv(50)
    assert len(compose(m, keep_turns=4)) < len(m)     # le prompt envoye est plus court


def test_purete_structurelle():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "multiservice" / "compose.py").read_text(encoding="utf-8")
    for interdit in ("urlopen", "Llama", "create_chat_completion", "subprocess", "append_events"):
        assert interdit not in src
