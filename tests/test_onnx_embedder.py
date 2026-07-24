"""Embedder ONNX local (MiniLM-L6-v2, 384d) — le calcul lourd reste CHEZ SOI.

Pourquoi : le central sert la memoire mais n'a ni GPU ni Ollama (charge VPS). Le corpus est
indexe sur le poste (GPU), seul le RESULTAT voyage ; le serveur n'embedde plus qu'une REQUETE
courte (~10-30 ms CPU). Contrainte constitutionnelle tenue : embedding 100% LOCAL, aucune API
d'inference hebergee.

Ici on teste les parties PURES (pooling, normalisation). La session ONNX est une coquille I/O
(meme statut qu'`OllamaEmbedder`), exercee par un test d'integration saute si le modele est absent.
"""
import math

import pytest

from multiservice import config
from multiservice.semantic import OnnxEmbedder, cosine, l2_normalize, mean_pool


def test_mean_pool_ignore_les_tokens_de_padding():
    """Le padding ne doit pas tirer le vecteur vers zero : seuls les tokens reels comptent."""
    tokens = [[2.0, 4.0], [4.0, 8.0], [999.0, 999.0]]   # 3e = padding
    mask = [1, 1, 0]
    assert mean_pool(tokens, mask) == [3.0, 6.0]


def test_mean_pool_masque_vide_ne_divise_pas_par_zero():
    """Robustesse : une entree entierement masquee rend un vecteur nul, jamais une exception."""
    assert mean_pool([[1.0, 2.0]], [0]) == [0.0, 0.0]


def test_l2_normalize_rend_un_vecteur_unitaire():
    v = l2_normalize([3.0, 4.0])
    assert math.isclose(math.sqrt(sum(x * x for x in v)), 1.0, rel_tol=1e-9)
    assert math.isclose(v[0], 0.6, rel_tol=1e-9)


def test_l2_normalize_vecteur_nul_reste_nul():
    """Un vecteur nul n'a pas de direction : on le rend tel quel plutot que de diviser par zero."""
    assert l2_normalize([0.0, 0.0]) == [0.0, 0.0]


def test_normalise_le_cosinus_devient_un_simple_produit_scalaire():
    """Interet du L2 : le re-score float32 se reduit a un produit scalaire (moins de calcul serveur)."""
    a, b = l2_normalize([1.0, 2.0, 3.0]), l2_normalize([2.0, 1.0, 0.5])
    assert math.isclose(cosine(a, b), sum(x * y for x, y in zip(a, b)), rel_tol=1e-9)


# --- integration : le vrai modele (saute s'il n'est pas installe sur la machine) ---

def _modele_absent():
    from pathlib import Path
    d = Path(config.ONNX_DIR)
    return not (d / "model.onnx").exists() or not (d / "tokenizer.json").exists()


pytestmark_integration = pytest.mark.skipif(_modele_absent(),
                                            reason="modele ONNX absent (cf. scripts/fetch_onnx_model.py)")


@pytestmark_integration
def test_embedder_onnx_produit_384_dimensions_normalisees():
    e = OnnxEmbedder(config.ONNX_DIR)
    vecs = e.embed(["la memoire observe, elle ne juge pas"])
    assert len(vecs) == 1 and len(vecs[0]) == 384
    assert math.isclose(math.sqrt(sum(x * x for x in vecs[0])), 1.0, rel_tol=1e-5)


@pytestmark_integration
def test_embedder_onnx_capte_le_sens_pas_les_caracteres():
    """Le point de tout l'exercice : deux formulations proches doivent etre plus proches
    que deux sujets etrangers. Sinon l'index ne vaut pas son transfert."""
    e = OnnxEmbedder(config.ONNX_DIR)
    a, b, c = e.embed(["le chiffrement au repos protege le journal",
                       "le journal est chiffre sur le disque",
                       "recette de la tarte aux pommes"])
    assert cosine(a, b) > cosine(a, c)


@pytestmark_integration
def test_embedder_onnx_traite_un_lot_et_tronque_les_textes_longs():
    e = OnnxEmbedder(config.ONNX_DIR)
    vecs = e.embed(["court", "x" * 50000])
    assert len(vecs) == 2 and all(len(v) == 384 for v in vecs)


@pytestmark_integration
def test_threads_ne_changent_pas_le_resultat():
    """Servir une REQUETE (1 thread, latence stable) et INDEXER un corpus (n threads) doivent
    produire exactement les memes vecteurs : sinon l'index construit au poste ne vaudrait plus
    pour les requetes servies au central."""
    texte = ["la source dit d'ou on ecrit, pas sur quoi"]
    mono = OnnxEmbedder(config.ONNX_DIR, threads=1).embed(texte)[0]
    multi = OnnxEmbedder(config.ONNX_DIR, threads=4).embed(texte)[0]
    assert all(math.isclose(a, b, abs_tol=1e-6) for a, b in zip(mono, multi))


# --- selection du backend d'embedding (pure, sans I/O) ---

def test_backend_par_defaut_reste_ollama():
    """RETRO-COMPAT : le poste local garde Ollama/bge-m3 tant qu'on ne demande rien d'autre."""
    from multiservice.semantic import OllamaEmbedder, make_embedder
    assert isinstance(make_embedder(backend=""), OllamaEmbedder)


def test_backend_onnx_choisi_explicitement():
    """Le central declare MULTISERVICE_EMBED_BACKEND=onnx : il embedde les REQUETES en CPU,
    sans Ollama et sans jamais indexer."""
    from multiservice.semantic import make_embedder
    assert isinstance(make_embedder(backend="onnx"), OnnxEmbedder)


def test_backend_onnx_sert_une_requete_en_un_seul_thread():
    """Latence stable cote serveur : servir n'est pas indexer."""
    from multiservice.semantic import make_embedder
    assert make_embedder(backend="onnx").threads == 1
