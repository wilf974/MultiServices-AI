"""Chiffrement des snapshots vers une CLE PUBLIQUE — pour les noeuds qu'on ne controle pas seul.

Le central (VPS) prend aussi un snapshot integral du journal avant chaque fusion : 52 fichiers,
276 Mo en clair au constat du 24/07/2026. Y poser une cle symetrique n'aurait servi a rien : qui
prend la machine prend la cle.

D'ou l'asymetrie : le VPS recoit la CLE PUBLIQUE et peut donc chiffrer, jamais dechiffrer. La cle
PRIVEE ne quitte pas le poste. C'est la propriete qui compte, et elle est testee explicitement.
"""
import pytest

from multiservice import crypto


def test_paire_generee_et_serialisable():
    priv, pub = crypto.gen_keypair()
    assert isinstance(priv, bytes) and isinstance(pub, bytes)
    assert priv != pub and len(pub) == 32


def test_round_trip_vers_la_cle_publique():
    priv, pub = crypto.gen_keypair()
    secret = b"une DEK de 32 octets ............"
    blob = crypto.seal_to_public(pub, secret)
    assert crypto.open_with_private(priv, blob) == secret


def test_la_cle_publique_seule_ne_dechiffre_pas():
    """LE point de tout l'exercice : le VPS n'a que la publique et doit rester incapable de lire."""
    priv, pub = crypto.gen_keypair()
    blob = crypto.seal_to_public(pub, b"secret")
    autre_priv, _ = crypto.gen_keypair()
    with pytest.raises(Exception):
        crypto.open_with_private(autre_priv, blob)


def test_deux_scellements_du_meme_secret_different():
    """Cle ephemere neuve a chaque fois : deux blobs identiques trahiraient un nonce fige."""
    _, pub = crypto.gen_keypair()
    assert crypto.seal_to_public(pub, b"idem") != crypto.seal_to_public(pub, b"idem")


def test_snapshot_scelle_vers_une_publique_puis_relu_avec_la_privee(tmp_path):
    """Bout en bout : le VPS chiffre avec la publique, le poste relit avec la privee."""
    from multiservice.snapshot_crypto import read_header, seal_public, unseal_private
    priv, pub = crypto.gen_keypair()
    clair = b'{"id":"1","text":"contenu du central"}\n' * 200
    blob = seal_public(clair, pub, meta={"nom": "journal-llm.jsonl.bak-20260724"})
    assert b"contenu du central" not in blob
    assert read_header(blob)["mode"] == "pub"          # l'en-tete dit comment ouvrir
    assert unseal_private(blob, priv) == clair


def test_snapshot_scelle_illisible_avec_une_autre_privee():
    from multiservice.snapshot_crypto import seal_public, unseal_private
    _, pub = crypto.gen_keypair()
    autre_priv, _ = crypto.gen_keypair()
    blob = seal_public(b"donnees", pub, meta={"nom": "x"})
    with pytest.raises(Exception):
        unseal_private(blob, autre_priv)


def test_entete_authentifie_aussi_en_mode_publique():
    from multiservice.snapshot_crypto import seal_public, unseal_private
    priv, pub = crypto.gen_keypair()
    blob = seal_public(b"donnees", pub, meta={"nom": "vrai-nom"})
    falsifie = blob.replace(b"vrai-nom", b"faux-nom")
    assert falsifie != blob
    with pytest.raises(Exception):
        unseal_private(falsifie, priv)


# --- CLI cote noeud distant : chiffrer un dossier avec la seule cle publique ---

def _dossier(tmp_path):
    d = tmp_path / "aethercore"
    d.mkdir()
    (d / "journal-llm.jsonl").write_bytes(b'{"id":"1","text":"journal vivant"}\n')
    (d / "journal-llm.jsonl.bak-20260724-120002").write_bytes(b'{"id":"1","text":"snapshot central"}\n')
    return d


def test_chiffrer_dossier_avec_une_publique_sans_aucun_keyring(tmp_path):
    """Le central n'a PAS de keyring et ne doit pas en avoir : la publique suffit a chiffrer."""
    from multiservice.encrypt_snapshots import chiffrer_dossier
    from multiservice.snapshot_crypto import read_header, unseal_private
    d = _dossier(tmp_path)
    priv, pub = crypto.gen_keypair()
    r = chiffrer_dossier(d, pub=pub)
    assert r["chiffres"] == 1
    enc = d / "journal-llm.jsonl.bak-20260724-120002.enc"
    assert b"snapshot central" not in enc.read_bytes()
    assert read_header(enc.read_bytes())["mode"] == "pub"
    assert b"snapshot central" in unseal_private(enc.read_bytes(), priv)


def test_le_journal_du_central_reste_intact(tmp_path):
    from multiservice.encrypt_snapshots import chiffrer_dossier
    d = _dossier(tmp_path)
    _, pub = crypto.gen_keypair()
    avant = (d / "journal-llm.jsonl").read_bytes()
    chiffrer_dossier(d, pub=pub)
    assert (d / "journal-llm.jsonl").read_bytes() == avant


def test_restauration_cote_poste_avec_la_privee(tmp_path):
    """Le poste rapatrie un .enc du central et le relit avec sa privee."""
    from multiservice.encrypt_snapshots import chiffrer_dossier, dechiffrer_fichier
    d = _dossier(tmp_path)
    priv, pub = crypto.gen_keypair()
    original = (d / "journal-llm.jsonl.bak-20260724-120002").read_bytes()
    chiffrer_dossier(d, pub=pub)
    sortie = dechiffrer_fichier(d / "journal-llm.jsonl.bak-20260724-120002.enc",
                                priv=priv, dest=tmp_path / "restaure.jsonl")
    assert sortie.read_bytes() == original
