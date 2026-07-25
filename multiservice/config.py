"""Configuration par defaut de MultiService AI (S13).

Surchargeable par variables d'environnement. Le journal LLM est SEPARE du journal
infra par defaut (prudence S13 : observer le flux LLM avant de fusionner les flux).
"""
from __future__ import annotations

import os
from pathlib import Path

# Racine locale du substrat (journaux, cache, skills) - a sauvegarder (O1b).
AETHER_HOME = os.environ.get("MULTISERVICE_HOME", str(Path.home() / ".aethercore"))

# --- backend Ollama (chemin recommande pour demarrer) ---
# Modele local par defaut. CHOIX UTILISATEUR, jamais fige (la contrainte constitutionnelle porte
# sur le LOCAL, pas sur un modele) : surchargeable par MULTISERVICE_OLLAMA_MODEL, --ollama-model,
# /model en session, ou le champ de la page webchat.
#
# 25/07/2026 — `eve-qwen3-8b` (modele de test des debuts) avait DISPARU d'Ollama : chaque appel
# repondait « model not found », le comparateur rendait « uncertain » et le rapport affichait
# quand meme le nom configure. On croyait juger, on ne jugeait rien.
# Mesure comparative sur une tache de jugement (temperature 0, 2 appels chacun) :
#   gemma4:12b      21,2 s puis 30,7 s — et INCOHERENT : « NON » puis « OUI » sur la meme question
#   qwen3.6:35b-a3b 42,7 s a froid puis 18,9 s a chaud — stable, et juste
# Le 35B est un MoE a ~3B actifs : plus gros sur disque, plus rapide a chaud ET deterministe.
# Pour un juge, la reproductibilite prime sur la taille du fichier.
OLLAMA_MODEL = os.environ.get("MULTISERVICE_OLLAMA_MODEL", "qwen3.6:35b-a3b-mtp-q4_K_M")
# 127.0.0.1 et NON `localhost` (25/07/2026) : sous Windows, `localhost` resout D'ABORD en ::1
# (IPv6) ou Ollama n'ecoute pas — chaque appel repondait 404, le comparateur rendait « uncertain »
# et le rapport affichait quand meme un resultat. On croyait juger, on ne jugeait rien.
# Mesure : localhost/api/chat -> 404 · 127.0.0.1/api/chat -> 200, meme instance, meme modele.
OLLAMA_HOST = os.environ.get("MULTISERVICE_OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_TIMEOUT = int(os.environ.get("MULTISERVICE_OLLAMA_TIMEOUT", "600"))  # s, generations longues

# --- backend EmbeddedGGUF (pur in-process, plus tard) ---
MODEL_PATH = os.environ.get(
    "MULTISERVICE_MODEL",
    "./models/your-model.gguf",   # backend EmbeddedGGUF : definis MULTISERVICE_MODEL vers ton .gguf
)
N_CTX = int(os.environ.get("MULTISERVICE_NCTX", "8192"))
N_GPU_LAYERS = int(os.environ.get("MULTISERVICE_NGPU", "-1"))

# --- journal LLM dedie (separe de ~/.aethercore/journal.jsonl pour le S13) ---
JOURNAL_PATH = os.environ.get(
    "MULTISERVICE_JOURNAL",
    str(Path.home() / ".aethercore" / "journal-llm.jsonl"),
)

# Magasin du cache de resultat (S16, separe du journal).
CACHE_PATH = os.environ.get(
    "MULTISERVICE_CACHE",
    str(Path.home() / ".aethercore" / "cache-llm.jsonl"),
)

# Magasin du cache SEMANTIQUE (S18, separe du cache exact et du journal).
SEMCACHE_PATH = os.environ.get(
    "MULTISERVICE_SEMCACHE",
    str(Path.home() / ".aethercore" / "semcache-llm.jsonl"),
)

# Embeddings locaux (D14) : cache vectoriel + modele Ollama d embedding.
EMBED_PATH = os.environ.get(
    "MULTISERVICE_EMBED",
    str(Path.home() / ".aethercore" / "embeddings-llm.jsonl"),
)
EMBED_MODEL = os.environ.get("MULTISERVICE_EMBED_MODEL", "bge-m3")

# Embedder ONNX local (MiniLM-L6-v2, 384d) : le corpus est indexe sur un poste avec GPU, seul le
# RESULTAT voyage ; le central n'embedde plus qu'une REQUETE courte (~10-30 ms CPU, pas d'Ollama,
# pas de reindexation). Embedding toujours 100% LOCAL : aucune API d'inference hebergee.
ONNX_DIR = os.environ.get(
    "MULTISERVICE_ONNX_DIR",
    str(Path.home() / ".aethercore" / "onnx" / "all-MiniLM-L6-v2"),
)

# Projection SQLite reconstructible (scaling Phase 1) : index de LECTURE, jamais une verite.
PROJECTION_PATH = os.environ.get(
    "MULTISERVICE_PROJECTION",
    str(Path.home() / ".aethercore" / "projection-llm.db"),
)

# Dossier des skills promues (S17), au format Agent Skills (SKILL.md).
SKILLS_DIR = os.environ.get(
    "MULTISERVICE_SKILLS",
    str(Path.home() / ".aethercore" / "skills"),
)

# Chiffrement au repos (opt-in, forward-only) : 1 -> append chiffre / read dechiffre par defaut.
# Le keyring (master + slots + wrapped_dek) vit HORS-journal ; le perdre = perdre le clair.
ENCRYPT_AT_REST = os.environ.get("MULTISERVICE_ENCRYPT", "") == "1"
KEYRING_DIR = os.environ.get(
    "MULTISERVICE_KEYRING",
    str(Path(AETHER_HOME) / "keyring"),
)

# Cloture C3 du contexte (S16) : nb de tours recents gardes en clair (qualite vs economie).
KEEP_TURNS = int(os.environ.get("MULTISERVICE_KEEP_TURNS", "6"))

# Thinking coupe au demarrage (D13) : aucun prompt systeme injecte par defaut.
SYSTEM_PROMPT = os.environ.get("MULTISERVICE_SYSTEM", "").strip()

# Depot de l'etat de curation (calcul lourd : 84 s) — lu par `resume` pour un cout nul.
CURATION_DIR = os.environ.get(
    "MULTISERVICE_CURATION_DIR",
    str(Path.home() / ".aethercore" / "curation"),
)
