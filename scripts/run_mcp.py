"""Lanceur du serveur MCP multiservice-memory.

Pourquoi ce fichier : `claude mcp add` bugue sur le flag `-m` (python -m ...), et lancer
`multiservice/mcp_server.py` en script direct casse (imports relatifs `from . import ...`).
Ce lanceur importe le PAQUET installe (`multiservice`, dispo apres `pip install -e .`) et appelle
son `main()` -> pas de `-m`, pas d'import relatif casse, pas d'exe a creer.

Brancher dans Claude Code (ou Desktop) :
  claude mcp add multiservice-memory --scope user -- C:\\Python313\\python.exe "<chemin>\\scripts\\run_mcp.py"
"""
from multiservice.mcp_server import main

if __name__ == "__main__":
    main()
