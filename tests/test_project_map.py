"""Dimension PROJET — resolution non destructive (C2/C3 intacts).

Pourquoi : la `source` dit D'OU on ecrit (imposee par le CN du cert), pas SUR QUOI. Tous les
projets d'un meme poste tombent dans un seul seau (`project:maison`), ce qui rend `project_review`
aveugle sur le journal reel. Le projet vit dans le `session_id`. On resout a la LECTURE, sans
jamais reecrire le passe.
"""
from multiservice.project_map import matches, project_of


def test_champ_project_explicite_fait_foi():
    """Un event portant `data['project']` (ecritures futures) est resolu sans regle."""
    assert project_of({"project": "project:MultiService-IA"}, "project:maison") == "project:multiservice"


def test_session_connue_resout_le_projet():
    """Le journal reel n'a pas de champ projet : la session porte l'information."""
    assert project_of({"session_id": "binah"}, "project:maison") == "project:binah"


def test_famille_de_sessions_resolue_par_prefixe():
    """Observe (24/07) : un projet s'etale sur des sessions `<projet>-<chantier>` —
    multiservice-chiffrement / -scaling / -ia / -readme = UN seul projet."""
    for sid in ("multiservice-chiffrement", "multiservice-scaling", "multiservice-readme"):
        assert project_of({"session_id": sid}, "project:maison") == "project:multiservice"


def test_filtre_par_projet_trouve_ce_que_la_source_noyait():
    """Le defaut corrige : une decision MultiService ecrite depuis le poste maison etait
    introuvable par projet (tout `project:maison`)."""
    data = {"session_id": "multiservice-chiffrement"}
    assert matches(data, "project:maison", "project:MultiService-IA") is True


def test_filtre_par_source_reste_intact():
    """RETRO-COMPAT : filtrer par source continue de marcher, meme pour un event dont le
    projet est resolu ailleurs."""
    data = {"session_id": "multiservice-chiffrement"}
    assert matches(data, "project:maison", "project:maison") is True


def test_filtre_isole_bien_les_projets():
    """Un autre projet du MEME poste ne doit pas fuir dans la vue."""
    data = {"session_id": "logos"}
    assert matches(data, "project:maison", "project:multiservice") is False


def test_filtre_vide_laisse_tout_passer():
    assert matches({"session_id": "logos"}, "project:maison", "") is True


def test_familles_observees_sur_le_journal_reel():
    """Gouvernance : seules les familles VRAIMENT observees figurent au registre (recensement
    du 24/07/2026 sur le journal local). Pas de regle inventee."""
    attendu = {
        "multiservice-chiffrement": "project:multiservice",
        "logos-cartographie": "project:logos",
        "binah": "project:binah",
        "aetherlife": "project:aetherlife",
        "lumiere": "project:lumiere",
        "pentest-agent": "project:pentest-agent",
        "noesis-capitalisation-1": "project:noesis",
        "finetune-distillation": "project:finetune",
    }
    for session, projet in attendu.items():
        assert project_of({"session_id": session}) == projet, session


def test_session_inconnue_ne_resout_rien():
    """Honnetete : pas de devinette. Une session hors registre n'a pas de projet resolu —
    le filtre retombe alors sur la source (retro-compat)."""
    assert project_of({"session_id": "surstock-journal"}) == ""
    assert matches({"session_id": "surstock-journal"}, "project:bureau", "project:bureau") is True
