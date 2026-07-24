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
OLLAMA_MODEL = os.environ.get("MULTISERVICE_OLLAMA_MODEL", "eve-qwen3-8b")
OLLAMA_HOST = os.environ.get("MULTISERVICE_OLLAMA_HOST", "http://localhost:11434")
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
