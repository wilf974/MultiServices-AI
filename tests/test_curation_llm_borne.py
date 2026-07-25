"""Jugement LLM BORNE : une tache planifiee doit toujours aboutir.

Constat du 25/07/2026 : le jugement LLM a tourne **plus de 40 minutes sans rien produire**, puis a
ete interrompu — fichier de sortie vide, aucun rapport. Le defaut n'est pas la lenteur, c'est le
TOUT OU RIEN : le module juge l'ensemble (46 candidats, modele 35B local) puis ecrit a la fin.
Interrompu a 95 %, il ne laisse rien.

Une tache planifiee hebdomadaire qui ne peut pas aboutir echoue en silence chaque semaine, et on
retrouve la curation a l'arret — exactement l'etat dont on venait de la sortir.

Remede, meme principe que le depot d'etat : **borner le lot** et ecrire a chaque passage. La
tache aboutit toujours, la file se vide par tranches, et on ne rejuge pas ce qui l'a deja ete.
"""
from multiservice import curation_llm


def _report(n=5):
    """Rapport deterministe minimal : n quasi-doublons."""
    return {"counts": {"near_duplicates": n},
            "near_duplicates": [{"type": "decision", "similarity": 0.9,
                                 "events": [{"id": "a%d" % i, "text": "fait %d" % i},
                                            {"id": "b%d" % i, "text": "fait %d bis" % i}]}
                                for i in range(n)],
            "contradiction_candidates": []}


def test_empreinte_stable_quel_que_soit_l_ordre():
    """Une paire (a,b) et (b,a) sont la MEME paire : sinon on la rejuge indefiniment."""
    e1 = curation_llm.empreinte_paire({"events": [{"id": "a"}, {"id": "b"}]})
    e2 = curation_llm.empreinte_paire({"events": [{"id": "b"}, {"id": "a"}]})
    assert e1 == e2


def test_borne_le_lot():
    """Le point : ne jamais tenter les 46 d'un coup."""
    sel = curation_llm.selectionner(_report(20), deja=set(), max_paires=5)
    assert len(sel["near_duplicates"]) == 5


def test_ne_rejuge_pas_ce_qui_l_a_deja_ete():
    r = _report(6)
    deja = {curation_llm.empreinte_paire(p) for p in r["near_duplicates"][:4]}
    sel = curation_llm.selectionner(r, deja=deja, max_paires=10)
    ids = {p["events"][0]["id"] for p in sel["near_duplicates"]}
    assert ids == {"a4", "a5"}


def test_les_compteurs_restent_honnetes():
    """La tranche traitee ne doit pas faire croire que la file est vide."""
    sel = curation_llm.selectionner(_report(20), deja=set(), max_paires=5)
    assert sel["counts"]["near_duplicates"] == 20     # total REEL
    assert sel["restant"] == 15


def test_file_vide_ne_leve_pas():
    sel = curation_llm.selectionner(_report(0), deja=set(), max_paires=5)
    assert sel["near_duplicates"] == [] and sel["restant"] == 0


def test_le_depot_des_paires_jugees_se_relit(tmp_path):
    curation_llm.deposer_juges(tmp_path, {"x", "y"})
    assert curation_llm.deja_juges(tmp_path) == {"x", "y"}


def test_depot_absent_rend_un_ensemble_vide(tmp_path):
    """Ne LEVE jamais : un depot absent ou illisible ne doit pas empecher de juger."""
    assert curation_llm.deja_juges(tmp_path) == set()


def test_un_passage_marque_les_paires_traitees(tmp_path):
    """Bout en bout : apres un passage, les paires jugees sont memorisees — le passage suivant
    prend la tranche d'apres, et la file se vide au lieu de tourner en rond."""
    class _BackendMuet:
        def generate(self, *a, **kw):
            return type("C", (), {"text": '{"verdict": "uncertain", "rationale": "x"}'})()

    r = _report(6)
    vus = curation_llm.marquer_traitees(tmp_path, curation_llm.selectionner(r, set(), 2))
    assert len(vus) == 2
    sel2 = curation_llm.selectionner(r, deja=curation_llm.deja_juges(tmp_path), max_paires=2)
    assert {p["events"][0]["id"] for p in sel2["near_duplicates"]} == {"a2", "a3"}
