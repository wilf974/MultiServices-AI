"""Sauvegarde du KEYRING — point de defaillance unique du chiffrement.

Perdre `master.key` (32 octets), c'est perdre TOUS les snapshots chiffres : aucune reconstruction
n'est possible, c'est tout l'interet. Il faut donc une copie ailleurs — mais une copie de secret
posee n'importe ou est elle-meme un risque. D'ou un bundle chiffre par PASSPHRASE : stockable
sur un cloud, un mail, un disque partage, sans exposer quoi que ce soit.

La regle de placement (non testable ici, mais dite une fois) : ne jamais poser le keyring en clair
sur le meme support que les donnees qu'il protege.
"""
import pytest

from multiservice import crypto
from multiservice.keyring_backup import export_bundle, import_bundle


def _keyring_peuple(tmp_path):
    from multiservice.keyring import KeyManager
    km = KeyManager(base=tmp_path / "keyring")
    km.get_or_create_slot("snapshots")
    km.get_or_create_slot("autre-slot")
    return km


def test_round_trip_restaure_master_et_slots(tmp_path):
    """Le devoir premier : ce qu'on ressort doit ouvrir ce que l'original ouvrait."""
    km = _keyring_peuple(tmp_path)
    master_avant = (tmp_path / "keyring" / "master.key").read_bytes()
    kek_avant = km.get_slot("snapshots")

    blob = export_bundle(tmp_path / "keyring", "une passphrase solide")
    r = import_bundle(blob, "une passphrase solide", tmp_path / "restaure")

    assert (tmp_path / "restaure" / "master.key").read_bytes() == master_avant
    assert r["slots"] == 2
    from multiservice.keyring import KeyManager
    assert KeyManager(base=tmp_path / "restaure").get_slot("snapshots") == kek_avant


def test_mauvaise_passphrase_refusee(tmp_path):
    _keyring_peuple(tmp_path)
    blob = export_bundle(tmp_path / "keyring", "la bonne")
    with pytest.raises(crypto.InvalidTag):
        import_bundle(blob, "la mauvaise", tmp_path / "restaure")


def test_le_bundle_ne_contient_aucune_cle_en_clair(tmp_path):
    km = _keyring_peuple(tmp_path)
    master = (tmp_path / "keyring" / "master.key").read_bytes()
    blob = export_bundle(tmp_path / "keyring", "passphrase")
    assert master not in blob
    assert km.get_slot("snapshots") not in blob


def test_deux_exports_different_meme_passphrase(tmp_path):
    """Sel et nonce neufs a chaque export : deux bundles identiques trahiraient un KDF fige."""
    _keyring_peuple(tmp_path)
    a = export_bundle(tmp_path / "keyring", "meme passphrase")
    b = export_bundle(tmp_path / "keyring", "meme passphrase")
    assert a != b


def test_passphrase_vide_refusee(tmp_path):
    """Un bundle sans passphrase serait un keyring en clair avec une etape de plus."""
    _keyring_peuple(tmp_path)
    with pytest.raises(ValueError):
        export_bundle(tmp_path / "keyring", "")


def test_le_keyring_restaure_dechiffre_un_vrai_snapshot(tmp_path):
    """Bout en bout, la seule preuve qui compte : chiffrer, PERDRE le keyring, le restaurer
    depuis le bundle, et relire le snapshot."""
    import shutil
    from multiservice.encrypt_snapshots import chiffrer_dossier, dechiffrer_fichier
    from multiservice.keyring import KeyManager

    d = tmp_path / "aethercore"
    d.mkdir()
    clair = b'{"id":"1","text":"contenu du journal"}\n' * 50
    (d / "journal-llm.jsonl.bak-20260724-120002").write_bytes(clair)

    km = KeyManager(base=tmp_path / "keyring")
    chiffrer_dossier(d, km)
    blob = export_bundle(tmp_path / "keyring", "passphrase de secours")

    shutil.rmtree(tmp_path / "keyring")                  # sinistre : le keyring disparait
    import_bundle(blob, "passphrase de secours", tmp_path / "keyring")

    sortie = dechiffrer_fichier(d / "journal-llm.jsonl.bak-20260724-120002.enc",
                                KeyManager(base=tmp_path / "keyring"),
                                dest=tmp_path / "restaure.jsonl")
    assert sortie.read_bytes() == clair
