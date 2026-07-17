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

from . import config, memory, projection
from .journal import read_events


def build_server(journal_path: str = None):
    """Construit le serveur FastMCP. Requiert le paquet `mcp` (import paresseux)."""
    from mcp.server.fastmcp import FastMCP   # import PARESSEUX (volontaire)

    jp = journal_path or config.JOURNAL_PATH
    srv = FastMCP("multiservice-memory")

    def _proj():
        """Projection a jour (scaling Phase 1) ou None -> repli fonctions pures sur le journal.
        Le repli garantit que la surface repond meme si la projection est indisponible (db
        verrouillee, FTS5 absent...) : la projection n'est jamais une dependance, juste un index."""
        try:
            return projection.for_journal(jp, config.PROJECTION_PATH)
        except Exception:
            return None

    @srv.tool()
    def recall(query: str, k: int = 10, type: str = "", source: str = "",
               has_code: bool = False, has_table: bool = False) -> list:
        """Contexte pertinent (lecture seule, bi-temporel, provenance attachee).
        Filtres optionnels : type ('prompt'/'completion'/...), source ('user'/'llm'/...),
        et STRUCTURE : has_code (souvenirs avec bloc de code), has_table (avec tableau markdown)."""
        p = _proj()
        kw = dict(k=k, type_=(type or None), source_prefix=(source or None),
                  has_code=has_code, has_table=has_table)
        if p is not None:
            return projection.recall_sql(p, query, **kw)
        return memory.recall(read_events(jp), query, **kw)

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
        kw = dict(k=k, type_=(type or None), source_prefix=(source or None),
                  explain=explain, min_fused=min_fused, sem_weight=sem_weight)
        p = _proj()
        if p is not None:
            return projection.recall_semantic_sql(p, query, embedder, store, **kw)
        return memory.recall_semantic(read_events(jp), query, embedder, store, **kw)

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
        p = _proj()
        if p is not None:
            return projection.brief_sql(p, query, k=k)
        return memory.topic_brief(read_events(jp), query, k=k)

    @srv.tool()
    def recent(days: int = 7, source: str = "", limit: int = 20) -> dict:
        """« Quoi de neuf » : evenements recents (fenetre `days`) = decisions + corrections +
        derniers evenements textuels. Point d'entree d'une reprise de travail. Lecture seule.
        `source` filtre par projet (ex 'project:MultiService-IA', graphies reconciliees) ;
        `limit` plafonne decisions/corrections (defaut 20, sortie bornee). Les compteurs
        `counts` restent complets et `truncated` signale la coupe."""
        p = _proj()
        if p is not None:
            return projection.recent_sql(p, days=days,
                                         source_prefix=(source or None), limit=limit)
        return memory.recent(read_events(jp), days=days,
                             source_prefix=(source or None), limit=limit)

    @srv.tool()
    def usage() -> dict:
        """Instrumentation (lecture seule) : reutilisation de la memoire — tours SERVIS depuis le
        cache (sans rappeler le modele), par source, et tokens d'entree epargnes. Mesure, pas predit."""
        return memory.reuse_stats(read_events(jp))

    @srv.tool()
    def reasoning(session_id: str) -> dict:
        """Fil de RAISONNEMENT d'une session : hypothese -> observation -> decision -> correction
        -> validation, ordonne. Indique les etapes presentes/manquantes (ex: decision sans
        validation). Lecture seule, cite ses preuves + fraicheur C3."""
        return memory.reasoning_chain(read_events(jp), session_id)

    @srv.tool()
    def lessons(source: str = "", k: int = 20, standing_k: int = 20) -> dict:
        """Lecons tirees des corrections (C3) : ce qui a ete revise/abandonne + la verite courante
        (`still_standing`). Lecture seule. Vide tant qu'aucune correction n'est journalisee.
        `source` filtre par projet ; `k` plafonne les lecons, `standing_k` les verites debout
        (defaut 20/20, sortie bornee). `counts` reste complet, `truncated` signale la coupe."""
        return memory.lessons_learned(read_events(jp), source_prefix=(source or None),
                                      k=k, standing_k=standing_k)

    @srv.tool()
    def project_review(project: str, days: int = 0, k: int = 20) -> dict:
        """Vue COMPOSEE de revue d'un PROJET (par source), bi-temporelle, lecture seule.
        Reconstruit l'etat depuis la seule memoire : decisions valides / corrigees (C3),
        hypotheses refutees / debout, validations, lecons — chacune sourcee, datee, avec son
        `corrected_by` (le « pourquoi ca a change »). `days=0` = tout l'historique (sinon N
        derniers jours). Sortie bornee (k), `counts` complet, `truncated` signale la coupe."""
        return memory.project_review(read_events(jp), project,
                                     days=(days or None), k=k)

    @srv.tool()
    def curation(source: str = "", k: int = 20, older_than_days: int = 30) -> dict:
        """Rapport de CURATION de la memoire (lecture seule, Phase 1) : doublons exacts et
        proches, gabarits non remplis encore valides, decisions anciennes non revisitees,
        contradictions candidates — plus des PROPOSITIONS en attente de validation humaine
        (AUCUNE ecriture, cloture jamais suppression). `source` filtre par projet ; sortie
        bornee (k), compteurs complets, `truncated` signale la coupe."""
        from . import curator
        return curator.curation_report(read_events(jp), source_prefix=(source or None),
                                       k=k, older_than_days=older_than_days)

    @srv.tool()
    def health() -> dict:
        """Sante du substrat memoire (lecture seule) : disponibilite (on a pu lire), nombre
        d'evenements, date du dernier, nombre de sources distinctes. Point d'entree d'une REPRISE
        (health -> recent -> recall) — ne devine rien, ne mute rien."""
        return memory.health(read_events(jp))

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


def build_http_server(host: str = None, port: int = None, journal_path: str = None):
    """Serveur FastMCP configure pour le transport streamable-http (conteneur).
    host/port surchargeables par env (MULTISERVICE_HTTP_HOST / MULTISERVICE_HTTP_PORT)."""
    import os
    from mcp.server.transport_security import TransportSecuritySettings
    h = host or os.environ.get("MULTISERVICE_HTTP_HOST", "0.0.0.0")
    p = int(port if port is not None else os.environ.get("MULTISERVICE_HTTP_PORT", "8302"))
    srv = build_server(journal_path)
    srv.settings.host = h
    srv.settings.port = p
    # Protection anti-DNS-rebinding : on la GARDE active et on autorise EXPLICITEMENT le(s) Host
    # public(s) servi(s) par le reverse proxy, via MULTISERVICE_HTTP_ALLOWED_HOSTS (separes par des
    # virgules, ex: "mem.example.com,127.0.0.1:8302"). Le proxy transmet le Host public, que le SDK
    # rejetterait sinon (421). Sans la variable : defaut du SDK (protection active, localhost) =
    # fail-closed, aucun Host public accepte. On ne desactive JAMAIS la protection (le bind par
    # defaut 0.0.0.0 reste sain car tout Host non autorise est refuse, pas seulement filtre au proxy).
    allowed = os.environ.get("MULTISERVICE_HTTP_ALLOWED_HOSTS", "").strip()
    if allowed:
        hosts = [x.strip() for x in allowed.split(",") if x.strip()]
        origins = [f"https://{x}" for x in hosts if "://" not in x and ":" not in x]
        srv.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=hosts,
            allowed_origins=origins,
        )
    return srv


def main_http() -> None:
    """Point d'entree HTTP : sert la memoire en LECTURE SEULE via streamable-http."""
    build_http_server().run(transport="streamable-http")


if __name__ == "__main__":
    main()
