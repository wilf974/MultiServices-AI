"""O1b - sauvegarde : couvre jsonl+skills, manifeste/verify, append-safe (jamais d'effacement)."""
from pathlib import Path

from multiservice.backup import backup, verify, MANIFEST


def _make_src(tmp):
    src = tmp / "src"; (src / "skills" / "hfsql").mkdir(parents=True)
    (src / "journal-llm.jsonl").write_text('{"a":1}\n', encoding="utf-8")
    (src / "cache-llm.jsonl").write_text('{"b":2}\n', encoding="utf-8")
    (src / "skills" / "hfsql" / "SKILL.md").write_text("# hfsql\n", encoding="utf-8")
    return src


def test_backup_couvre_jsonl_et_skills(tmp_path):
    src = _make_src(tmp_path); dest = tmp_path / "dest"
    m = backup(src, dest)
    keys = set(m["files"])
    assert "journal-llm.jsonl" in keys and "cache-llm.jsonl" in keys
    assert "skills/hfsql/SKILL.md" in keys
    assert (dest / "skills" / "hfsql" / "SKILL.md").exists()


def test_verify_ok_puis_detecte_corruption(tmp_path):
    src = _make_src(tmp_path); dest = tmp_path / "dest"
    backup(src, dest)
    assert verify(dest) == []                                  # intact
    (dest / "journal-llm.jsonl").write_text("ALTERE\n", encoding="utf-8")
    probs = verify(dest)
    assert any("corrompu" in p for p in probs)                 # corruption detectee


def test_append_safe_n_efface_jamais(tmp_path):
    src = _make_src(tmp_path); dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "vieux-backup.jsonl").write_text("garde-moi\n", encoding="utf-8")
    backup(src, dest)
    assert (dest / "vieux-backup.jsonl").exists()              # l'existant n'est jamais supprime


def test_verify_sans_manifeste(tmp_path):
    assert verify(tmp_path / "vide") != []
