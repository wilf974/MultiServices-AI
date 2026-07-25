"""Fermer la BOUCLE de curation — un diagnostic que personne ne voit ne sert a rien.

Constat du 25/07/2026, chiffres a l'appui :
  - `curation_report` coute **84 s** (comparaison de paires, quadratique) -> impossible a
    recalculer a chaud dans une reprise ;
  - il y a **0 proposition** en attente : les 43 quasi-doublons et 141 decisions anciennes sont
    des SIGNALEMENTS, pas des propositions. Seuls les doublons exacts en produisent, et ils ont
    ete traites le 06/07 ;
  - le maillon qui transforme un signalement en proposition — le juge LLM — n'etait pas branche,
    et il prend > 10 min : il ne peut pas etre synchrone non plus.

Donc la boucle se ferme ainsi : la tache calcule (lentement, une fois par jour) et DEPOSE son
resultat ; la reprise le LIT (cout nul) et le met sous les yeux avec sa commande d'approbation.
L'humain tranche (C1) — la memoire ne s'auto-cure jamais.
"""
import json
from datetime import datetime, timedelta, timezone

from multiservice import memory
from multiservice.events import AetherEvent, EventType

T0 = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)


def _ev(typ, texte, minute=0, src="project:demo"):
    return AetherEvent(type=typ, title=typ.value, description=texte, source=src,
                       observed_at=T0 + timedelta(minutes=minute),
                       data={"text": texte, "session_id": "s1", "turn_id": "t%d" % minute})


def _etat(**kw):
    base = {"as_of": T0.isoformat(), "counts": {"proposals": 0, "near_duplicates": 0,
                                                "stale_candidates": 0}, "proposals": []}
    base.update(kw)
    return base


def test_resume_remonte_les_propositions_en_attente():
    """Le maillon manquant : ce qui attend une decision doit arriver SOUS LES YEUX."""
    prop = {"action": "close_duplicate", "targets": ["id-2"], "keep": "id-1",
            "rationale": "deux fois le meme fait",
            "command": 'memlog-http "..." --kind correction --closes id-2'}
    r = memory.resume([_ev(EventType.DECISION, "un fait")], "project:demo", now=T0,
                      curation=_etat(counts={"proposals": 1}, proposals=[prop]))
    assert r["curation"]["en_attente"] == 1
    assert r["curation"]["propositions"][0]["command"].startswith("memlog-http")


def test_rien_a_decider_ne_fait_pas_de_bruit():
    """Une file vide ne doit pas encombrer la reprise."""
    r = memory.resume([_ev(EventType.DECISION, "un fait")], "project:demo", now=T0,
                      curation=_etat())
    assert r["curation"]["en_attente"] == 0 and r["curation"]["propositions"] == []


def test_un_rapport_perime_est_un_angle_mort():
    """Un diagnostic vieux de deux semaines decrit une memoire qui n'existe plus."""
    vieux = _etat(as_of=(T0 - timedelta(days=14)).isoformat())
    r = memory.resume([_ev(EventType.DECISION, "un fait")], "project:demo", now=T0,
                      curation=vieux)
    assert r["sante"]["degraded"] is True
    assert any("curation" in w.lower() for w in r["sante"]["warnings"])


def test_un_rapport_frais_ne_declenche_rien():
    r = memory.resume([_ev(EventType.DECISION, "un fait")], "project:demo", now=T0,
                      curation=_etat(as_of=(T0 - timedelta(hours=6)).isoformat()))
    assert not any("curation" in w.lower() for w in r["sante"]["warnings"])


def test_sans_rapport_du_tout_la_reprise_fonctionne():
    """RETRO-COMPAT : `resume` sans curation reste valide (la tache peut n'avoir jamais tourne)."""
    r = memory.resume([_ev(EventType.DECISION, "un fait")], "project:demo", now=T0)
    assert r["curation"]["en_attente"] == 0


def test_les_signalements_sont_distingues_des_propositions():
    """43 quasi-doublons ne sont pas 43 actions : un signalement demande un JUGEMENT, une
    proposition demande une DECISION. Les confondre fait paraitre la file enorme et decourage."""
    r = memory.resume([_ev(EventType.DECISION, "un fait")], "project:demo", now=T0,
                      curation=_etat(counts={"proposals": 2, "near_duplicates": 43,
                                             "stale_candidates": 141}))
    assert r["curation"]["en_attente"] == 2
    assert r["curation"]["a_juger"] == 43 + 141


def test_le_depot_du_rapport_est_relisible(tmp_path):
    """La tache calcule lentement et DEPOSE ; la reprise lit. Le format doit tenir le contrat."""
    from multiservice import curation_report as cr
    etat = _etat(counts={"proposals": 1}, proposals=[{"action": "close_duplicate",
                                                      "command": "memlog-http ..."}])
    p = cr.deposer_etat(tmp_path, etat)
    relu = json.loads(p.read_text(encoding="utf-8"))
    assert relu["counts"]["proposals"] == 1
    assert cr.dernier_etat(tmp_path)["counts"]["proposals"] == 1


def test_dossier_sans_depot_rend_none(tmp_path):
    from multiservice import curation_report as cr
    assert cr.dernier_etat(tmp_path) is None


# --- le depot doit fonctionner EN CONDITIONS REELLES, pas seulement en test unitaire ---

def test_run_depose_l_etat_la_ou_le_serveur_le_lit(tmp_path, monkeypatch):
    """Deux bugs reels du 25/07 attrapes ici : (1) `deposer_etat` etait defini APRES le bloc
    `if __name__ == '__main__'`, donc NameError a l'execution — un test unitaire de la fonction
    seule ne l'aurait jamais vu ; (2) la tache deposait dans le dossier des RAPPORTS alors que la
    reprise lisait `config.CURATION_DIR` : deux chemins, jamais la meme boite aux lettres."""
    from multiservice import config, curation_report as cr
    from multiservice.journal import append_events
    jp = tmp_path / "j.jsonl"
    append_events(jp, [_ev(EventType.DECISION, "un fait"), _ev(EventType.DECISION, "un fait", 1)])
    depot = tmp_path / "depot"
    monkeypatch.setattr(config, "CURATION_DIR", str(depot))

    cr.run(str(jp), str(tmp_path / "rapports"), now=T0)

    etat = cr.dernier_etat(config.CURATION_DIR)      # LA ou le serveur ira lire
    assert etat is not None, "l'etat doit etre depose a l'emplacement canonique"
    assert "counts" in etat and "as_of" in etat


def test_le_cli_complet_ne_casse_pas(tmp_path):
    """Le module doit s'executer de bout en bout (`python -m`), pas seulement s'importer."""
    import subprocess, sys
    from multiservice.journal import append_events
    jp = tmp_path / "j.jsonl"
    append_events(jp, [_ev(EventType.DECISION, "un fait")])
    r = subprocess.run([sys.executable, "-m", "multiservice.curation_report",
                        "--journal", str(jp), "--out", str(tmp_path / "out")],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, "code retour %d : %s" % (r.returncode, r.stderr[-400:])
