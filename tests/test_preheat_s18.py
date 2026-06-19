"""Sprint 18 - test de regression : pre-chauffage (estimation, LECTURE SEULE).

Contrat (feuille de route S18 (b)) : le pre-chauffage NE MUTE RIEN, n'appelle aucun modele,
cite ses preuves, et reste une ESTIMATION (jamais une verite engagee). Cas vides/inconnus surs.

Valide sur COPIE PROPRE (cf. CLAUDE.md).
"""
import copy
from datetime import datetime, timedelta, timezone

from multiservice.backends import Completion
from multiservice.preheat import forecast_next_turn
from multiservice.router import events_for_turn

T0 = datetime(2026, 6, 18, 9, 0, tzinfo=timezone.utc)
SID = "sess-1"


def _session(inputs, out=20):
    """Une session dont les tours ont les tokens d'entree donnes (snowball)."""
    evs = []
    for i, nin in enumerate(inputs):
        t = T0 + timedelta(minutes=5 * i)
        evs += events_for_turn(f"tour {i}", Completion(f"rep {i}", "eve", nin, out),
                               "local_tokenizer", session_id=SID, now=t)
    return evs


def test_projette_le_snowball():
    f = forecast_next_turn(_session([100, 250, 450]))
    assert f["found"] is True
    assert f["observed_turns"] == 3
    assert f["last_input"] == 450
    assert f["avg_growth_per_turn"] == 175.0          # (150+200)/2
    assert f["projected_next_input"] == 625           # 450 + 175
    assert f["projected_next_output"] == 20


def test_contraste_fenetrage_c3_en_snowball():
    f = forecast_next_turn(_session([100, 250, 450]), keep_turns=2)
    # vrai snowball (pente 175 >> last_in/(2*keep)=112) -> fenetrage 175*2=350 < 625.
    assert f["regime"].startswith("snowball")
    assert f["projected_windowed_input"] == 350
    assert f["windowing_would_save"] == 625 - 350


def test_plateau_ne_reclame_aucune_economie():
    """Crise revelee par le reel (19 juin) : une session DEJA fenetree (entrees plates ~3300,
    pente faible) ne doit PAS annoncer une fausse economie de fenetrage."""
    plateau = [3135, 3231, 3226, 3639, 3387, 3333, 3300, 3290, 3310, 3333]
    f = forecast_next_turn(_session(plateau))
    assert f["regime"].startswith("contexte deja borne")
    assert f["windowing_would_save"] == 0
    assert f["projected_windowed_input"] == f["projected_next_input"]


def test_ne_mute_rien():
    evs = _session([100, 250, 450])
    snap = copy.deepcopy([e.model_dump() for e in evs])
    forecast_next_turn(evs)
    assert [e.model_dump() for e in evs] == snap, "le pre-chauffage doit etre PUR"


def test_cite_ses_preuves():
    f = forecast_next_turn(_session([100, 250, 450]))
    assert f["evidence_inputs_tail"] == [100, 250, 450]
    assert "estimation" in f["basis"]


def test_session_unique_pente_nulle():
    f = forecast_next_turn(_session([300]))
    assert f["found"] is True
    assert f["avg_growth_per_turn"] == 0.0
    assert f["projected_next_input"] == 300           # pas de pente -> on ne sur-estime pas


def test_vide_et_inconnu_sont_surs():
    assert forecast_next_turn([])["found"] is False
    assert forecast_next_turn(_session([100, 200]), session_id="autre")["found"] is False
