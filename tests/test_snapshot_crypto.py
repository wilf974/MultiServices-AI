"""Chiffrement des SNAPSHOTS (.bak-*) du journal — enveloppe au niveau FICHIER.

Les snapshots sont des copies integrales du journal, prises des deux cotes avant chaque fusion
(`sync_memory_merge.ps1`). Ils heritent donc de tout le contenu sensible, sans aucune des gardes
du journal. Meme hierarchie de cles que le chiffrement au repos (design ⑦) : DEK par fichier,
wrappee sous la KEK d'un slot, materiel-cle HORS du fichier -> detruire la cle rend le snapshot
illisible sans le reecrire (crypto-shred).

Un backup qu'on ne sait pas restaurer ne vaut rien : le round-trip est le premier test.
"""
import pytest

from multiservice import crypto
from multiservice.snapshot_crypto import seal, unseal


def test_round_trip_rend_exactement_le_clair():
    """Le premier devoir d'une sauvegarde : revenir a l'octet pres."""
    kek = crypto.gen_key()
    clair = b'{"id":"abc","text":"secret metier"}\n' * 500
    blob = seal(clair, kek, slot_id="snapshots", meta={"nom": "journal-llm.jsonl.bak-20260724"})
    assert unseal(blob, kek) == clair


def test_le_clair_n_apparait_pas_dans_le_blob():
    kek = crypto.gen_key()
    clair = b'{"text":"cracker un compte facebook"}'
    blob = seal(clair, kek, slot_id="snapshots", meta={"nom": "x"})
    assert b"facebook" not in blob


def test_mauvaise_cle_refuse_de_dechiffrer():
    kek = crypto.gen_key()
    blob = seal(b"donnees", kek, slot_id="snapshots", meta={"nom": "x"})
    with pytest.raises(crypto.InvalidTag):
        unseal(blob, crypto.gen_key())


def test_alteration_du_ciphertext_detectee():
    """AEAD : un octet retourne doit faire echouer, pas rendre du faux clair."""
    kek = crypto.gen_key()
    blob = bytearray(seal(b"donnees importantes", kek, slot_id="snapshots", meta={"nom": "x"}))
    blob[-1] ^= 0x01
    with pytest.raises(crypto.InvalidTag):
        unseal(bytes(blob), kek)


def test_alteration_de_l_entete_detectee():
    """L'en-tete clair (nom d'origine, taille, empreinte) est AUTHENTIFIE : le falsifier doit
    echouer. Sinon on pourrait faire passer un snapshot pour un autre."""
    kek = crypto.gen_key()
    blob = seal(b"donnees", kek, slot_id="snapshots", meta={"nom": "vrai-nom"})
    falsifie = blob.replace(b"vrai-nom", b"faux-nom")
    assert falsifie != blob
    with pytest.raises(crypto.InvalidTag):
        unseal(falsifie, kek)


def test_entete_lisible_sans_la_cle():
    """On doit pouvoir inventorier des snapshots chiffres (nom, taille, date) SANS pouvoir les lire."""
    from multiservice.snapshot_crypto import read_header
    kek = crypto.gen_key()
    blob = seal(b"x" * 1234, kek, slot_id="snapshots", meta={"nom": "journal.bak-20260724"})
    h = read_header(blob)
    assert h["meta"]["nom"] == "journal.bak-20260724"
    assert h["taille_clair"] == 1234
    assert h["slot"] == "snapshots"
    assert "ct" not in h and "dek" in h        # la DEK y est, mais WRAPPEE


# --- I/O : chiffrer les snapshots d'un dossier, et savoir les restaurer ---

def _keyring(tmp_path):
    from multiservice.keyring import KeyManager
    return KeyManager(base=tmp_path / "keyring")


def _dossier(tmp_path):
    d = tmp_path / "aethercore"
    d.mkdir()
    (d / "journal-llm.jsonl").write_bytes(b'{"id":"1","text":"le journal vivant"}\n')
    (d / "journal-llm.jsonl.bak-20260724-120002").write_bytes(b'{"id":"1","text":"snapshot A"}\n')
    (d / "journal-llm.jsonl.bak-20260724-130002").write_bytes(b'{"id":"2","text":"snapshot B"}\n')
    return d


def test_chiffre_les_snapshots_et_retire_le_clair(tmp_path):
    from multiservice.encrypt_snapshots import chiffrer_dossier
    d, km = _dossier(tmp_path), _keyring(tmp_path)
    r = chiffrer_dossier(d, km)
    assert r["chiffres"] == 2
    assert sorted(p.name for p in d.glob("*.bak-*.enc")) == [
        "journal-llm.jsonl.bak-20260724-120002.enc", "journal-llm.jsonl.bak-20260724-130002.enc"]
    assert list(d.glob("*.bak-2*[!c]")) == []                 # plus aucun snapshot en clair
    assert b"snapshot A" not in (d / "journal-llm.jsonl.bak-20260724-120002.enc").read_bytes()


def test_ne_touche_jamais_au_journal_lui_meme(tmp_path):
    """Le journal-verite n'est PAS un snapshot : le chiffrer ici le rendrait illisible aux
    lecteurs (MCP, projection) qui ne savent rien de cette enveloppe."""
    from multiservice.encrypt_snapshots import chiffrer_dossier
    d, km = _dossier(tmp_path), _keyring(tmp_path)
    avant = (d / "journal-llm.jsonl").read_bytes()
    chiffrer_dossier(d, km)
    assert (d / "journal-llm.jsonl").read_bytes() == avant
    assert not (d / "journal-llm.jsonl.enc").exists()


def test_restauration_rend_l_original_a_l_octet_pres(tmp_path):
    from multiservice.encrypt_snapshots import chiffrer_dossier, dechiffrer_fichier
    d, km = _dossier(tmp_path), _keyring(tmp_path)
    original = (d / "journal-llm.jsonl.bak-20260724-120002").read_bytes()
    chiffrer_dossier(d, km)
    sortie = dechiffrer_fichier(d / "journal-llm.jsonl.bak-20260724-120002.enc", km,
                                dest=tmp_path / "restaure.jsonl")
    assert sortie.read_bytes() == original


def test_idempotent_ne_rechiffre_pas(tmp_path):
    """Relancer la tache ne doit rien refaire : sinon on empile les enveloppes a chaque passage."""
    from multiservice.encrypt_snapshots import chiffrer_dossier
    d, km = _dossier(tmp_path), _keyring(tmp_path)
    chiffrer_dossier(d, km)
    r2 = chiffrer_dossier(d, km)
    assert r2["chiffres"] == 0 and r2["deja_chiffres"] == 2


def test_snapshot_illisible_si_la_cle_du_slot_est_detruite(tmp_path):
    """Crypto-shred : detruire la KEK du slot suffit, sans reecrire un seul snapshot."""
    from multiservice.encrypt_snapshots import chiffrer_dossier, dechiffrer_fichier
    d, km = _dossier(tmp_path), _keyring(tmp_path)
    chiffrer_dossier(d, km)
    km.destroy("snapshots")
    with pytest.raises(Exception):
        dechiffrer_fichier(d / "journal-llm.jsonl.bak-20260724-120002.enc", km,
                           dest=tmp_path / "x.jsonl")


def test_le_chiffre_herite_de_la_date_du_snapshot(tmp_path):
    """La purge par retention (sync_memory_scheduled) filtre sur LastWriteTime. Si le .enc
    portait la date du CHIFFREMENT, un vieux snapshot rajeunirait et survivrait trop longtemps."""
    import os, time
    from multiservice.encrypt_snapshots import chiffrer_dossier
    d, km = _dossier(tmp_path), _keyring(tmp_path)
    vieux = d / "journal-llm.jsonl.bak-20260724-120002"
    jadis = time.time() - 10 * 86400
    os.utime(vieux, (jadis, jadis))
    chiffrer_dossier(d, km)
    enc = d / "journal-llm.jsonl.bak-20260724-120002.enc"
    assert abs(enc.stat().st_mtime - jadis) < 2
