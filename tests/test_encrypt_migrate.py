"""CLI encrypt_migrate (Brief 1, design sec.8) — bulk re-encrypt SUPERVISE du stock en clair.

Dry-run par defaut (plan pur, ne touche rien) ; `--bulk` = operation supervisee unique (C1) :
re-chiffre les events en clair (slot-par-source), trace un event `migration` EN CLAIR, sauvegarde
l'ancien journal + ses sceaux, REBASELINE la chaine (nouveau sceau). Idempotent : les events deja
chiffres (et les tombstones) sont conserves octet pour octet, jamais re-enveloppes."""
from multiservice import encrypt_migrate, envelope, integrity, keyring
from multiservice.events import AetherEvent, EventType
from multiservice.journal import append_events, read_events


def _ev(**kw):
    d = dict(type=EventType.NOTE, title="titre secret", description="desc secrete",
             source="human:local", data={"x": 1})
    d.update(kw)
    return AetherEvent(**d)


def _setup(tmp_path):
    """Journal en clair : 2 events (2 sources) + 1 intent erasure. Keyring jetable."""
    journal = tmp_path / "j.jsonl"
    append_events(journal, [_ev(source="human:a", title="secret a"),
                            _ev(source="human:b", title="secret b"),
                            AetherEvent(type=EventType.ERASURE, title="erasure",
                                        source="human:operator", data={"targets": ["slot:x"]})],
                  keyring=None)
    return journal, keyring.KeyManager(base=tmp_path / "keyring")


# ---- plan : PUR, compte sans rien toucher ----
def test_plan_compte_clair_chiffres_intents(tmp_path):
    journal, km = _setup(tmp_path)
    events = read_events(journal, keyring=None)
    p = encrypt_migrate.plan(events)
    assert (p["total"], p["clair"], p["chiffres"], p["intents"]) == (3, 2, 0, 1)
    assert p["par_source"] == {"human:a": 1, "human:b": 1}


# ---- bulk : chiffre le stock, trace migration en clair, l'intent erasure reste en clair ----
def test_bulk_chiffre_le_stock_et_trace_migration(tmp_path):
    journal, km = _setup(tmp_path)
    r = encrypt_migrate.bulk_migrate(journal, km, authorized_by="human:<user>")
    assert r["migrated"] == 2
    raw = journal.read_text(encoding="utf-8")
    assert "secret a" not in raw and "secret b" not in raw       # le disque ne voit plus le clair
    raw_evs = read_events(journal, keyring=None)
    assert raw_evs[-1].type == EventType.MIGRATION               # trace C1, EN CLAIR, derniere ligne
    assert raw_evs[-1].data["migrated"] == 2
    assert not envelope.is_encrypted(raw_evs[2])                 # l'intent erasure jamais chiffre
    clairs = {e.title for e in read_events(journal, keyring=km)}
    assert {"secret a", "secret b"} <= clairs                    # contenu relisible via keyring


# ---- bulk : chaine REBASELINEE (ancien sceau archive, nouveau sceau valide) + backup du clair ----
def test_bulk_rebaseline_chaine_et_backup(tmp_path):
    journal, km = _setup(tmp_path)
    integrity.seal(journal)                                      # sceau de l'ere « clair »
    encrypt_migrate.bulk_migrate(journal, km, authorized_by="human:<user>")
    st = integrity.status(journal)
    assert st["ok"] and st["seals"] == 1                         # UN sceau : la nouvelle baseline
    backup = journal.with_name(journal.name + ".pre-encrypt.bak")
    assert "secret a" in backup.read_text(encoding="utf-8")      # l'ancien clair sauvegarde (politique)


# ---- bulk idempotent : 2e run ne re-chiffre rien, les tombstones ne ressuscitent pas ----
def test_bulk_idempotent_et_tombstones_preserves(tmp_path):
    journal, km = _setup(tmp_path)
    encrypt_migrate.bulk_migrate(journal, km, authorized_by="human:<user>")
    km.destroy("slot:human:a")                                   # shred d'une source apres migration
    lines_before = {ln for ln in journal.read_text(encoding="utf-8").splitlines()
                    if '"migration"' not in ln}
    r2 = encrypt_migrate.bulk_migrate(journal, km, authorized_by="human:<user>")
    assert r2["migrated"] == 0                                   # rien a re-chiffrer
    lines_after = {ln for ln in journal.read_text(encoding="utf-8").splitlines()
                   if '"migration"' not in ln}
    assert lines_before <= lines_after                           # events chiffres conserves OCTET pour octet
    by_source = {e.source: e for e in read_events(journal, keyring=km) if e.type == EventType.NOTE}
    assert by_source["human:a"].title == "[efface]"              # le shred survit a la re-migration
    assert by_source["human:b"].title == "secret b"
