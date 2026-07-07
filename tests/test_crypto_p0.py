"""P0 chiffrement — crypto.py : SEUL point d'import de `cryptography`. Primitives PURES bytes->bytes.
On teste l'AEAD (chiffre/dechiffre, liaison AAD) et le wrap/unwrap de cle (KEK-wrappe-DEK)."""
import pytest

from multiservice import crypto


def test_aead_roundtrip():
    k, n = crypto.gen_key(), crypto.gen_nonce()
    ct = crypto.aead_encrypt(k, n, b"contenu secret", b"aad-header")
    assert ct != b"contenu secret"
    assert crypto.aead_decrypt(k, n, ct, b"aad-header") == b"contenu secret"


def test_aead_mauvais_aad_leve():
    k, n = crypto.gen_key(), crypto.gen_nonce()
    ct = crypto.aead_encrypt(k, n, b"x", b"aad-a")
    with pytest.raises(crypto.InvalidTag):
        crypto.aead_decrypt(k, n, ct, b"aad-b")           # AAD different -> tag KO


def test_aead_ct_falsifie_leve():
    k, n = crypto.gen_key(), crypto.gen_nonce()
    ct = bytearray(crypto.aead_encrypt(k, n, b"xyz", b"a"))
    ct[0] ^= 0x01                                          # un octet retourne
    with pytest.raises(crypto.InvalidTag):
        crypto.aead_decrypt(k, n, bytes(ct), b"a")


def test_wrap_unwrap_dek():
    kek, dek = crypto.gen_key(), crypto.gen_key()
    n, wrapped = crypto.wrap_key(kek, dek)
    assert wrapped != dek
    assert crypto.unwrap_key(kek, n, wrapped) == dek


def test_unwrap_mauvaise_kek_leve():
    dek = crypto.gen_key()
    n, wrapped = crypto.wrap_key(crypto.gen_key(), dek)
    with pytest.raises(crypto.InvalidTag):
        crypto.unwrap_key(crypto.gen_key(), n, wrapped)   # autre KEK -> impossible


def test_gen_key_et_nonce_tailles():
    assert len(crypto.gen_key()) == 32 and len(crypto.gen_nonce()) == 12
    assert crypto.gen_key() != crypto.gen_key()            # aleatoire
