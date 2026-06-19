"""Sprint 14 - Serveur MCP en LECTURE SEULE (coquille I/O ; logique dans memory.py).

Expose la memoire a un client MCP (Claude Desktop, etc.) :
  tools      : recall(query,k) · why(turn_id)
  resources  : aether://briefing/today
AUCUN outil n'ecrit le journal (D5 : la 2e surface donne acces, pas mutation).

Import PARESSEUX du SDK `mcp` : ce module s'importe sans `mcp` installe (les tests de la
logique tournent sans le SDK). Lancer le serveur : `pip install mcp` puis `python -m
multiservice.mcp_server`.
"""
from __future__ import annotations

import json

from . import config, memory
from .journal import read_events


def build_server(journal_path: str = None):
    """Construit le serveur FastMCP. Requiert le paquet `mcp` (import paresseux)."""
    from mcp.server.fastmcp import FastMCP   # import PARESSEUX (volontaire)

    jp = journal_path or config.JOURNAL_PATH
    srv = FastMCP("multiservice-memory")

    @srv.tool()
    def recall(query: str, k: int = 10, type: str = "", source: str = "",
               has_code: bool = False, has_table: bool = False) -> list:
        """Contexte pertinent (lecture seule, bi-temporel, provenance attachee).
        Filtres optionnels : type ('prompt'/'completion'/...), source ('user'/'llm'/...),
        et STRUCTURE : has_code (souvenirs avec bloc de code), has_table (avec tableau markdown)."""
        return memory.recall(read_events(jp), query, k=k,
                             type_=(type or None), source_prefix=(source or None),
                             has_code=has_code, has_table=has_table)

    @srv.tool()
    def why(turn_id: str) -> list:
        """Les evenements d'un tour donne (pourquoi l'agent a vu/dit ca)."""
        return memory.why(read_events(jp), turn_id)

    @srv.tool()
    def recall_semantic(query: str, k: int = 10, type: str = "", source: str = "", explain: bool = False, min_fused: float = 0.4, sem_weight: float = 0.7) -> list:
        """Recall HYBRIDE (semantique local + bi-temporel). Suggestif ; repli lexical si non indexe.
        Pre-requis : avoir lance `python -m multiservice.index` (embeddings locaux Ollama)."""
        from .semantic import EmbeddingStore, OllamaEmbedder
        store = EmbeddingStore(config.EMBED_PATH)
        embedder = OllamaEmbedder(model=config.EMBED_MODEL, host=config.OLLAMA_HOST)
        return memory.recall_semantic(read_events(jp), query, embedder, store, k=k,
                                      type_=(type or None), source_prefix=(source or None),
                                      explain=explain, min_fused=min_fused, sem_weight=sem_weight)

    @srv.tool()
    def replay(session_id: str, digest: bool = True):
        """Rejoue une session - lecture seule. digest=True (defaut) = resume COMPACT econome
        (1 ligne/tour) ; digest=False = tous les evenements ordonnes (dump complet)."""
        ev = read_events(jp)
        return memory.session_digest(ev, session_id) if digest else memory.replay_session(ev, session_id)

    @srv.tool()
    def replay_event(event_id: str, depth: int = 3) -> dict:
        """Chaine causale d'un EVENEMENT : pourquoi l'agent a vu/dit ca. Remonte le tour focus
        + 'depth' tours precedents de la session + cloture/correction C3. Lecture seule, cite
        ses preuves (id, source, dates). Donne un event_id issu d'un recall."""
        return memory.replay_event(read_events(jp), event_id, depth=depth)

    @srv.tool()
    def forecast(session_id: str = "") -> dict:
        """Pre-chauffage (lecture seule, ESTIMATION) : cout projete du prochain tour d'une
        session (snowball vs fenetrage C3). session_id vide = derniere session. N'engage rien."""
        from . import preheat
        return preheat.forecast_next_turn(read_events(jp), session_id=(session_id or None))

    @srv.tool()
    def brief(query: str, k: int = 5) -> dict:
        """Brief composE sur un SUJET (un appel = souvenirs + dEcisions + rEvisEs C3 + sessions).
        DEduplicquE et classE. Lecture seule. Remplace plusieurs recall/why a la main."""
        return memory.topic_brief(read_events(jp), query, k=k)

    @srv.tool()
    def recent(days: int = 7) -> dict:
        """« Quoi de neuf » : evenements recents (fenetre `days`) = decisions + corrections +
        derniers evenements textuels. Point d'entree d'une reprise de travail. Lecture seule."""
        return memory.recent(read_events(jp), days=days)

    @srv.tool()
    def index_status() -> dict:
        """FraIcheur de l'index sEmantique : combien d'EvEnements indexables sont couverts.
        Si 'fresh' est faux, recall_semantic ne voit pas tout (rEsultats partiels). Lecture seule."""
        from .semantic import EmbeddingStore
        return memory.index_coverage(read_events(jp), EmbeddingStore(config.EMBED_PATH).load())

    @srv.resource("aether://briefing/today")
    def briefing_today() -> str:
        """Briefing d'usage du jour (tokens, economie compaction, par modele)."""
        return json.dumps(memory.briefing_today(read_events(jp)), ensure_ascii=False)

    return srv


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
