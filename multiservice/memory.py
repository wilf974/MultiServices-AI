"""Sprint 14 - Memoire restituee (LECTURE SEULE), sur le journal jsonl.

recall / why / briefing_today : on LIT le journal, on ne mute jamais rien. Provenance et
bi-temporalite attachees (C2/C3). recall est LEXICAL aujourd'hui (D14 : l'hybride vectoriel
viendra en couche suggestive, embedding LOCAL). Tout est PUR : List[AetherEvent] -> resultat.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .events import AetherEvent, EventType
from .skills import _norm, _tokens
from .project_map import matches as project_matches
from .source_alias import canonical


def _source_matches(ev_source: Optional[str], prefix: Optional[str]) -> bool:
    """Filtre source CANONIQUE : reconcilie les graphies (project:MultiService-IA ~ project:multiservice)
    sans toucher le journal brut. prefix vide -> tout passe. PUR."""
    if not prefix:
        return True
    return canonical(ev_source).startswith(canonical(prefix))

_TABLE_RE = re.compile(r"\|[^\n]*-{3,}[^\n]*\|")    # ligne de separation d'un tableau markdown


def _has_code(text: str) -> bool:
    """Vrai si le texte contient un bloc de code (fence ```). PUR."""
    return "```" in (text or "")


def _has_table(text: str) -> bool:
    """Vrai si le texte contient un tableau markdown (ligne de separation |---|). PUR."""
    return bool(_TABLE_RE.search(text or ""))


_TURN_ORDER = {"prompt": 0, "tool_call": 1, "tool_result": 2,
               "completion": 3, "token_usage": 4, "correction": 5}


def _type_rank(t: str) -> int:
    return _TURN_ORDER.get(t, 9)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _text(e: AetherEvent) -> str:
    return (e.data.get("text") or e.description or e.title or "")


def _coupe(txt: str, defaut: int, chars: Optional[int] = None) -> str:
    """Borne un texte de sortie. `chars=None` -> la borne HISTORIQUE de l'appelant (economie de
    sortie, comportement inchange) ; `chars=0` -> texte INTEGRAL ; `chars=N` -> coupe a N.

    Pourquoi : un agent qui veut lire UN souvenir en entier ne doit pas avoir a enchainer trois
    outils pour le decouvrir encore tronque (constat d'usage du 24/07/2026)."""
    txt = txt or ""
    n = defaut if chars is None else chars
    if not n or len(txt) <= n:
        return txt
    return txt[:n]


CHAMPS_STRUCTURES = ("rationale", "pitfall", "command", "refs")


def _structure(e: AetherEvent) -> Dict[str, Any]:
    """Champs structures presents sur l'event, absents sinon. PUR.

    Economie de sortie : un champ vide n'encombre pas la reponse. Ce qu'on ecrit structure doit se
    RELIRE structure, sinon l'effort d'ecriture est perdu et le lecteur re-parse de la prose."""
    return {c: e.data[c] for c in CHAMPS_STRUCTURES
            if isinstance(e.data, dict) and e.data.get(c) not in (None, "", [], {})}


VERDICTS = ("useful", "useless", "prevented_error")   # ensemble FERME : un verdict libre rendrait
                                                       # l'agregation ininterpretable


def utilite(events: List[AetherEvent]) -> Dict[str, Dict[str, int]]:
    """Ce que chaque souvenir a SERVI, agrege par verdict. PUR, LECTURE SEULE.

    V2 (25/07/2026) : aucun signal ne disait quel souvenir avait evite une erreur, lequel n'avait
    jamais ete relu — `usage` mesure des tokens, pas de la valeur. Sans ce retour, la curation
    DEVINE ce qu'il faut perimer.

    Un retour est un evenement comme un autre (append-only, C3) qui POINTE vers le souvenir servi,
    sur le patron de `data.closes` : `data.rates=[ids]` + `data.verdict`. Un souvenir sans retour
    n'apparait pas : l'absence de signal n'est pas un signal."""
    out: Dict[str, Dict[str, int]] = {}
    for e in events:
        data = e.data if isinstance(e.data, dict) else {}
        cibles = data.get("rates")
        verdict = data.get("verdict")
        if not isinstance(cibles, list) or verdict not in VERDICTS:
            continue
        for cid in cibles:
            if isinstance(cid, str) and cid:
                out.setdefault(cid, {v: 0 for v in VERDICTS})[verdict] += 1
    return out


def protege_par_utilite(events: List[AetherEvent], event_id: str) -> bool:
    """Ce souvenir a-t-il deja EVITE UNE ERREUR ? PUR.

    LE point de V2 : un garde-fou qui a servi une seule fois vaut d'etre garde — c'est
    precisement celui qu'on peririmerait, faute de l'avoir vu agir. La curation doit le laisser
    tranquille."""
    return utilite(events).get(event_id, {}).get("prevented_error", 0) > 0


RELATIONS = ("confirms", "contradicts", "refines")


def consensus(events: List[AetherEvent]) -> Dict[str, Dict[str, Any]]:
    """Ce que les AUTRES agents disent de chaque fait. PUR, LECTURE SEULE.

    V3 (25/07/2026) : quatre sources ecrivent dans le meme journal et personne ne repond a
    personne. Un fait dit une fois pese autant qu'un fait verifie par trois.

    Ce qui compte n'est PAS le nombre de confirmations mais la DIVERSITE des sources : trois
    confirmations du meme agent ne valent pas trois agents independants, sinon un agent bavard
    fabriquerait de la certitude tout seul. Et se confirmer soi-meme n'apporte rien : la source
    d'origine est exclue de ses propres confirmations.

    Un fait sans relation n'apparait pas (l'absence de signal n'est pas un signal)."""
    origine = {e.id: canonical(e.source) for e in events}
    brut: Dict[str, Dict[str, set]] = {}
    for e in events:
        data = e.data if isinstance(e.data, dict) else {}
        src = canonical(e.source)
        for rel in RELATIONS:
            cibles = data.get(rel)
            if not isinstance(cibles, list):
                continue
            for cid in cibles:
                if not isinstance(cid, str) or not cid:
                    continue
                if src and src == origine.get(cid):
                    continue                          # se confirmer soi-meme n'informe personne
                brut.setdefault(cid, {r: set() for r in RELATIONS})[rel].add(src)
    return {cid: {**{r: sorted(s for s in rels[r] if s) for r in RELATIONS},
                  "agents_confirmants": len({s for s in rels["confirms"] if s}),
                  "agents_contredisants": len({s for s in rels["contradicts"] if s})}
            for cid, rels in brut.items()}


def contradictions_ouvertes(events: List[AetherEvent], source_prefix: Optional[str] = None,
                            as_of_: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Faits CONTREDITS par un autre agent et pas encore TRANCHES. PUR, LECTURE SEULE.

    Une contradiction ne clot rien (C1 : l'humain arbitre) — elle remonte comme « a trancher ».
    Trancher, c'est clore le fait depasse par une cloture CIBLEE, jamais le supprimer (C3) :
    un fait clos disparait donc naturellement de cette liste."""
    asof = _aware(as_of_) or datetime.now(timezone.utc)
    closes_idx = _closes_index(events, as_of=asof)
    cons = consensus(events)
    par_id = {e.id: e for e in events}
    out = []
    for cid, c in cons.items():
        if not c["contradicts"]:
            continue
        e = par_id.get(cid)
        if e is None or _closed_by(closes_idx, cid):
            continue                                  # deja tranche
        if not project_matches(e.data, e.source, source_prefix):
            continue
        vt = _aware(e.valid_to)
        if vt and vt <= asof:
            continue
        vf = _aware(e.valid_from)
        out.append({"id": cid, "source": e.source,
                    "valid_from": vf.isoformat() if vf else None,
                    "text": _coupe(_text(e), 300),
                    "contredit_par": c["contradicts"],
                    "confirme_par": c["confirms"]})
    out.sort(key=lambda d: d["valid_from"] or "", reverse=True)
    return out


def _corrections_index(events: List[AetherEvent]) -> Dict[Any, list]:
    """Index des `correction` par session : {session_id: [(valid_from, id), ...]}. PUR.
    Sert le drapeau de fraicheur C3 : un hit corrige plus tard ne doit pas etre cite sans reserve."""
    idx: Dict[Any, list] = {}
    for e in events:
        if e.type == EventType.CORRECTION:
            sid = e.data.get("session_id")
            if sid is None:
                continue
            idx.setdefault(sid, []).append((_aware(e.valid_from), e.id))
    return idx


def _superseded_by(corr_idx: Dict[Any, list], session_id: Any,
                   vf: Optional[datetime]) -> List[str]:
    """Ids des corrections de la MEME session POSTERIEURES a vf (sinon liste vide). PUR."""
    if session_id is None or vf is None:
        return []
    return [cid for (cvf, cid) in corr_idx.get(session_id, []) if cvf and cvf > vf]


def _closes_index(events: List[AetherEvent],
                  as_of: Optional[datetime] = None) -> Dict[str, List[str]]:
    """Cloture CIBLEE (curation Phase 2) : {event_id vise: [ids des corrections qui le closent]}.
    Une CORRECTION valide a as_of portant `data.closes=[ids]` clot PRECISEMENT ces evenements
    — et rien d'autre : elle vit dans une session neutre (ex 'curation-closures') pour ne pas
    declencher le supersede session+temps sur la session d'origine (l'original a garder y
    survivrait pas sinon). PUR, LECTURE SEULE."""
    asof = _aware(as_of) or datetime.now(timezone.utc)
    idx: Dict[str, List[str]] = {}
    for e in events:
        if e.type != EventType.CORRECTION:
            continue
        closes = e.data.get("closes")
        if not isinstance(closes, list) or not closes:
            continue
        vf = _aware(e.valid_from)
        if vf and vf > asof:
            continue                                 # pas encore valide (bi-temporel)
        vt = _aware(e.valid_to)
        if vt and vt < asof:
            continue                                 # la cloture elle-meme est close (C3)
        for target in closes:
            if isinstance(target, str) and target:
                idx.setdefault(target, []).append(e.id)
    return idx


def _closed_by(closes_idx: Dict[str, List[str]], event_id: str) -> List[str]:
    """Ids des corrections qui CLOSENT precisement cet evenement (liste vide sinon). PUR."""
    return list(closes_idx.get(event_id, []))


def as_of(events: List[AetherEvent], at: Optional[datetime] = None) -> List[AetherEvent]:
    """Etat ACTIF au TEMPS VALIDE `at` (C3) : valid_from <= at, pas de cloture explicite
    (valid_to < at), pas de cloture CIBLEE en vigueur a `at` (`data.closes`, quelle que soit
    sa date d'ARRIVEE — c'est l'overlay du design snapshots, docs/SCALING-PROJECTIONS.md par.3).
    Le supersede par session reste un DRAPEAU de lecture (recall), pas une cloture.
    Ordre du journal preserve. PUR, LECTURE SEULE — c'est l'ORACLE de `projection.as_of_sql`."""
    asof = _aware(at) or datetime.now(timezone.utc)
    closes_idx = _closes_index(events, as_of=asof)
    out = []
    for e in events:
        vf = _aware(e.valid_from)
        if vf and vf > asof:
            continue                                 # pas encore valide a as_of
        vt = _aware(e.valid_to)
        if vt and vt < asof:
            continue                                 # cloture explicite avant as_of (C3)
        if _closed_by(closes_idx, e.id):
            continue                                 # cloture ciblee en vigueur a as_of
        out.append(e)
    return out


def as_of_view(events: List[AetherEvent], at: Optional[datetime] = None, chars: Optional[int] = None,
               source_prefix: Optional[str] = None, k: int = 50) -> Dict[str, Any]:
    """Vue BORNEE de l'etat actif au temps valide `at` (surface MCP) : « qu'est-ce qui etait
    vrai a T ? ». Compteurs COMPLETS (`count`, `by_type`), items RECENTS d'abord, sortie
    bornee (k), `truncated` signale la coupe. `source_prefix` filtre par projet (compteurs
    inclus). Idempotent sur une liste deja active (as_of l'est). PUR, LECTURE SEULE."""
    asof = _aware(at) or datetime.now(timezone.utc)
    active = [e for e in as_of(events, asof)
              if _source_matches(e.source, source_prefix)]
    by_type: Dict[str, int] = {}
    for e in active:
        by_type[e.type.value] = by_type.get(e.type.value, 0) + 1
    recent_first = sorted(active, key=lambda e: (_aware(e.valid_from) or asof), reverse=True)
    items = []
    for e in recent_first[:max(0, k)]:
        txt = _text(e)
        vf = _aware(e.valid_from)
        items.append({
            "id": e.id, "type": e.type.value, "source": e.source,
            "valid_from": vf.isoformat() if vf else None,
            "session_id": e.data.get("session_id"),
            "text": txt if not chars and chars is not None else (
                txt if len(txt) <= (chars or 200) else txt[:(chars or 200)].rstrip() + "..."),
        })
    return {"at": asof.isoformat(), "count": len(active), "by_type": by_type,
            "truncated": len(active) > k, "items": items}


def _snippet(text: str, query: str, width: int = 200) -> str:
    """Extrait centre sur le 1er terme de la requete trouve, avec ellipses. PUR, econome.
    Renvoie le texte entier s'il est deja court. Evite le dump : la sortie reste legere."""
    if not text or len(text) <= width:
        return text
    low = _norm(text)
    pos = -1
    for t in _tokens(query):
        i = low.find(t)
        if i != -1:
            pos = i
            break
    if pos < 0:
        return text[:width].rstrip() + "..."
    start = max(0, pos - width // 3)
    end = min(len(text), start + width)
    snip = text[start:end].strip()
    if start > 0:
        snip = "..." + snip
    if end < len(text):
        snip = snip + "..."
    return snip


def _score(query: str, text: str) -> float:
    """Pertinence lexicale = COUVERTURE des mots de la requete (deterministe, accent-insensible).
    Fraction des tokens DISTINCTS de la requete presents dans le texte, dans [0,1]. Pas de poids
    a la frequence brute (un doc verbeux generique ne gonfle plus). Phrase exacte -> couverture pleine."""
    low = _norm(text)
    qtokens = set(_tokens(query))
    if not qtokens:                                  # requete vide/mots-vides : repli sous-chaine
        qn = _norm(query).strip()
        return 1.0 if qn and qn in low else 0.0
    present = sum(1 for t in qtokens if t in low)
    if present == 0:
        return 0.0
    cov = present / len(qtokens)
    if _norm(query).strip() in low:                  # phrase exacte presente
        cov = 1.0
    return round(cov, 4)


def recall(events: List[AetherEvent], query: str, as_of: Optional[datetime] = None,
           k: int = 10, type_: Optional[str] = None,
           source_prefix: Optional[str] = None,
           has_code: bool = False, has_table: bool = False) -> List[Dict[str, Any]]:
    """Top-k evenements valides a as_of, classes par PERTINENCE (puis recence).
    LECTURE SEULE, filtre bi-temporel (C3), lexical par tokens (D14), accent-insensible.
    Filtres optionnels : type_ (ex 'prompt','completion'), source_prefix (ex 'user','llm'),
    et STRUCTURE : has_code (bloc ```), has_table (tableau markdown). Teste sur le texte complet."""
    asof = _aware(as_of) or datetime.now(timezone.utc)
    corr_idx = _corrections_index(events)            # C3 : fraicheur (correction posterieure ?)
    closes_idx = _closes_index(events, as_of=asof)   # clotures CIBLEES (curation)
    util = utilite(events)                           # V2 : ce que chaque souvenir a SERVI
    cons = consensus(events)                         # V3 : ce que les AUTRES agents en disent
    hits = []
    for e in events:
        if type_ and e.type.value != type_:
            continue
        if not project_matches(e.data, e.source, source_prefix):
            continue
        vf = _aware(e.valid_from)
        if vf and vf > asof:
            continue                                 # pas encore valide a as_of
        vt = _aware(e.valid_to)
        if vt and vt < asof:
            continue                                 # cloture avant as_of (C3)
        txt = _text(e)
        if has_code and not _has_code(txt):          # filtre structure (sur texte complet)
            continue
        if has_table and not _has_table(txt):
            continue
        sc = _score(query, txt)
        if sc <= 0:
            continue                                 # aucun mot de la requete present
        corrected = (_superseded_by(corr_idx, e.data.get("session_id"), vf)
                     + _closed_by(closes_idx, e.id))
        hits.append({
            "id": e.id, "type": e.type.value, "source": e.source,
            "valid_from": vf.isoformat() if vf else None,
            "turn_id": e.data.get("turn_id"), "session_id": e.data.get("session_id"),
            "score": round(sc, 1), "text": _snippet(txt, query),
            "superseded": bool(corrected),           # C3 : corrige plus tard ? (a citer avec reserve)
            "corrected_by": corrected,
            **_structure(e),                         # rationale / pitfall / command / refs si ecrits
            **({"utilite": util[e.id]} if e.id in util else {}),   # V2 : ce que ca a SERVI
            **({"consensus": cons[e.id]} if e.id in cons else {}),  # V3 : ce que les autres en disent
        })
    hits.sort(key=lambda h: (h["score"], h["valid_from"] or ""), reverse=True)
    return hits[:k]


def why(events: List[AetherEvent], turn_id: str,
        chars: Optional[int] = None) -> List[Dict[str, Any]]:
    """Le 'pourquoi' d'un tour : ses evenements (prompt/completion/token...), ordonnes.
    (Le replay event -> chaine causale plus profond viendra au S18.)"""
    evs = [e for e in events if e.data.get("turn_id") == turn_id]
    evs.sort(key=lambda e: (_aware(e.valid_from) or datetime.min.replace(tzinfo=timezone.utc),
                            _type_rank(e.type.value)))
    return [{
        "id": e.id, "type": e.type.value, "source": e.source,
        "valid_from": (_aware(e.valid_from).isoformat() if e.valid_from else None),
        "text": _coupe(_text(e), 500, chars), "data": {k: v for k, v in e.data.items() if k != "text"},
    } for e in evs]


def replay_session(events: List[AetherEvent], session_id: str,
                   chars: Optional[int] = None) -> List[Dict[str, Any]]:
    """Rejoue une SESSION entiere : tous ses evenements, ordonnes (lecture seule).
    Utile a un agent qui a un session_id (issu d'un recall) et veut tout le fil."""
    evs = [e for e in events if e.data.get("session_id") == session_id]
    evs.sort(key=lambda e: (_aware(e.valid_from) or datetime.min.replace(tzinfo=timezone.utc),
                            _type_rank(e.type.value)))
    return [{
        "id": e.id, "type": e.type.value, "source": e.source,
        "valid_from": (_aware(e.valid_from).isoformat() if e.valid_from else None),
        "turn_id": e.data.get("turn_id"), "text": _coupe(_text(e), 300, chars),
    } for e in evs]


def session_digest(events: List[AetherEvent], session_id: str,
                   width: int = 120) -> Dict[str, Any]:
    """Resume COMPACT d'une session : 1 ligne par tour (prompt+completion tronques, tokens).
    PUR, LECTURE SEULE. Alternative econome au dump complet de `replay_session` (longues sessions)."""
    floor = datetime.min.replace(tzinfo=timezone.utc)
    turns: Dict[str, List[AetherEvent]] = {}
    for e in events:
        if e.data.get("session_id") != session_id:
            continue
        t = e.data.get("turn_id")
        if not t:
            continue
        turns.setdefault(t, []).append(e)
    rows = []
    for t, evs in sorted(turns.items(),
                         key=lambda kv: min((_aware(x.valid_from) or floor) for x in kv[1])):
        by = {x.type.value: x for x in evs}
        vf = min((_aware(x.valid_from) for x in evs if x.valid_from), default=None)
        tok = by.get("token_usage")
        rows.append({
            "turn_id": t,
            "valid_from": vf.isoformat() if vf else None,
            "prompt": _text(by["prompt"])[:width] if "prompt" in by else "",
            "completion": _text(by["completion"])[:width] if "completion" in by else "",
            "in": int(tok.data.get("input_tokens", 0)) if tok else 0,
            "out": int(tok.data.get("output_tokens", 0)) if tok else 0,
        })
    span = [rows[0]["valid_from"], rows[-1]["valid_from"]] if rows else []
    return {"session_id": session_id, "turns": len(rows), "span": span, "rows": rows}


def _ev_brief(e: AetherEvent, chars: Optional[int] = None) -> Dict[str, Any]:
    """Vue courte d'un evenement pour une chaine causale (preuve : id + source + dates)."""
    return {
        "id": e.id, "type": e.type.value, "source": e.source,
        "valid_from": (_aware(e.valid_from).isoformat() if e.valid_from else None),
        "valid_to": (_aware(e.valid_to).isoformat() if e.valid_to else None),
        "turn_id": e.data.get("turn_id"), "text": _coupe(_text(e), 300, chars),
    }


def replay_event(events: List[AetherEvent], event_id: str, chars: Optional[int] = None,
                 depth: int = 3) -> Dict[str, Any]:
    """Chaine causale d'un EVENEMENT (event -> contexte qui a mene a lui). PUR, LECTURE SEULE.

    Repond 'pourquoi l'agent a vu/dit ca' en remontant :
      - le tour de l'evenement (cause immediate : prompt/tool/completion du meme turn_id),
      - les 'depth' tours PRECEDENTS de la meme session (contexte antecedent),
      - la bi-temporalite C3 : cloture propre (valid_to) et corrections posterieures qui le bornent.
    Cite ses preuves (id, source, dates). Ne cree, ne ferme, ne mute RIEN. id inconnu -> found=False.
    """
    target = next((e for e in events if e.id == event_id), None)
    if target is None:
        return {"event_id": event_id, "found": False, "antecedents": []}

    tid = target.data.get("turn_id")
    sid = target.data.get("session_id")
    tvf = _aware(target.valid_from) or datetime.min.replace(tzinfo=timezone.utc)

    # C3 : corrections de la meme session, posterieures ou simultanees au focus.
    corrections = []
    if sid is not None:
        corrections = sorted(
            (e for e in events
             if e.type == EventType.CORRECTION
             and e.data.get("session_id") == sid
             and (_aware(e.valid_from) or tvf) >= tvf),
            key=lambda e: _aware(e.valid_from) or tvf,
        )
    bitemporal = {
        "valid_to": (_aware(target.valid_to).isoformat() if target.valid_to else None),
        "closed": target.valid_to is not None,                  # C3 : cloture, jamais suppression
        "corrected_by": [e.id for e in corrections],
    }

    focus = _ev_brief(target, chars)
    if not tid:                                                 # ex : decision hors tour
        return {"event_id": event_id, "found": True, "focus": focus,
                "bitemporal": bitemporal, "antecedents": []}

    # Grouper par tour dans la session, ordonner par debut de tour.
    turns: Dict[str, List[AetherEvent]] = {}
    for e in events:
        if sid is not None and e.data.get("session_id") != sid:
            continue
        t = e.data.get("turn_id")
        if not t:
            continue
        turns.setdefault(t, []).append(e)

    def turn_start(evs: List[AetherEvent]) -> datetime:
        return min((_aware(x.valid_from) or tvf) for x in evs)

    ordered = sorted(turns.items(), key=lambda kv: turn_start(kv[1]))
    idx = next((i for i, (t, _) in enumerate(ordered) if t == tid), None)
    if idx is None:
        chain = [(tid, turns.get(tid, [target]))]
    else:
        lo = max(0, idx - max(0, depth))
        chain = ordered[lo: idx + 1]                            # antecedents -> tour focus

    antecedents = []
    for t, evs in chain:
        evs_sorted = sorted(
            evs, key=lambda e: (_aware(e.valid_from) or tvf, _type_rank(e.type.value)))
        antecedents.append({
            "turn_id": t,
            "valid_from": turn_start(evs).isoformat(),
            "is_focus_turn": (t == tid),
            "events": [_ev_brief(e, chars) for e in evs_sorted],
        })
    return {"event_id": event_id, "found": True, "focus": focus,
            "bitemporal": bitemporal, "antecedents": antecedents}


def topic_brief(events: List[AetherEvent], query: str, k: int = 5,
                as_of: Optional[datetime] = None) -> Dict[str, Any]:
    """Brief composE sur un SUJET (un appel au lieu de plusieurs). PUR, LECTURE SEULE.

    Compose `recall` pour rendre, dEduplicquE et classE :
      - memories : souvenirs pertinents (hors dEcisions),
      - decisions : les dEcisions qui s'y rapportent (type=decision),
      - revised   : ceux qui ont E tE corrigEs depuis (C3 : a citer avec rEserve),
      - sessions  : les sessions touchEes (pour replay/why si besoin).
    Ne cree, ne ferme, ne mute RIEN."""
    mems = recall(events, query, as_of=as_of, k=k * 2)
    decisions = recall(events, query, as_of=as_of, k=k, type_="decision")
    dec_ids = {d["id"] for d in decisions}
    memories = [m for m in mems if m["id"] not in dec_ids][:k]
    revised = [h for h in (memories + decisions) if h.get("superseded")]
    sessions: List[str] = []
    for h in memories + decisions:
        sid = h.get("session_id")
        if sid and sid not in sessions:
            sessions.append(sid)
    return {
        "query": query,
        "memories": memories,
        "decisions": decisions,
        "revised": revised,                          # C3 : corrigE plus tard, a citer avec rEserve
        "sessions": sessions,                        # pour `replay`/`why` si besoin
        "counts": {"memories": len(memories), "decisions": len(decisions),
                   "revised": len(revised), "sessions": len(sessions)},
    }


def recent(events: List[AetherEvent], days: int = 7, chars: Optional[int] = None,
           now: Optional[datetime] = None, k: int = 10,
           source_prefix: Optional[str] = None,
           limit: Optional[int] = 20) -> Dict[str, Any]:
    """« Quoi de neuf » : evenements de la fenetre `days`, du plus recent au plus ancien. PUR,
    LECTURE SEULE. Point d'entree d'une REPRISE : separe `decisions` et `corrections`, et donne
    les `latest` k evenements textuels recents (extrait). S'appuie sur la bi-temporalite (C3).

    Economie de SORTIE (calibree sur le reel : journal central multi-projets, recent(14)
    debordait a ~70 Ko / 705 events) : `source_prefix` restreint a un projet (graphies
    reconciliees par l'alias canonique) ; `limit` plafonne `decisions` et `corrections`
    (les plus recentes d'abord ; None = tout). Rien n'est cache en silence : `counts`
    reste COMPLET et `truncated` signale la coupe."""
    now = _aware(now) or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    rec = []
    for e in events:
        if not project_matches(e.data, e.source, source_prefix):
            continue
        vf = _aware(e.valid_from)
        if vf is None or vf < cutoff or vf > now:
            continue
        rec.append(e)
    rec.sort(key=lambda e: _aware(e.valid_from), reverse=True)   # plus recent d'abord

    def brief(e: AetherEvent) -> Dict[str, Any]:
        return {"id": e.id, "type": e.type.value, "source": e.source,
                "valid_from": _aware(e.valid_from).isoformat(),
                "session_id": e.data.get("session_id"), "text": _coupe(_text(e), 160, chars)}

    decisions = [e for e in rec if e.type == EventType.DECISION]
    corrections = [e for e in rec if e.type == EventType.CORRECTION]
    lim = None if limit is None else max(0, limit)
    return {
        "since": cutoff.isoformat(), "days": days, "count": len(rec),
        "counts": {"decisions": len(decisions), "corrections": len(corrections)},
        "truncated": bool(lim is not None
                          and (len(decisions) > lim or len(corrections) > lim)),
        "decisions": [brief(e) for e in decisions[:lim]],
        "corrections": [brief(e) for e in corrections[:lim]],
        "latest": [brief(e) for e in rec if _text(e).strip()][:k],
    }


# Types « faits » qu'une correction peut perimer (on exclut prompt/token_usage).
_FACT_TYPES = {EventType.DECISION, EventType.COMPLETION, EventType.NOTE, EventType.TOOL_RESULT}

# Etapes d'un fil de RAISONNEMENT, dans l'ordre canonique (graphe causal).
_REASONING_ORDER = ["hypothesis", "observation", "decision", "correction", "validation"]
_REASONING_SET = set(_REASONING_ORDER)


def reasoning_chain(events: List[AetherEvent], session_id: str, chars: Optional[int] = None,
                    as_of: Optional[datetime] = None) -> Dict[str, Any]:
    """Le fil de RAISONNEMENT d'une session : hypothese -> observation -> decision -> correction
    -> validation, ordonne chronologiquement (puis par etape). PUR, LECTURE SEULE.

    Signale les etapes `present` / `missing` (ex: une decision SANS validation) — fait observe,
    pas un jugement. Chaque pas porte sa provenance et sa fraicheur C3 (`superseded`)."""
    asof = _aware(as_of) or datetime.now(timezone.utc)
    corr_idx = _corrections_index(events)
    rank = {s: i for i, s in enumerate(_REASONING_ORDER)}
    steps = []
    for e in events:
        if e.data.get("session_id") != session_id:
            continue
        if e.type.value not in _REASONING_SET:
            continue
        vf = _aware(e.valid_from)
        if vf and vf > asof:
            continue
        vt = _aware(e.valid_to)
        if vt and vt < asof:
            continue
        cor = _superseded_by(corr_idx, session_id, vf)
        steps.append({
            "id": e.id, "stage": e.type.value, "source": e.source,
            "valid_from": vf.isoformat() if vf else None, "text": _coupe(_text(e), 200, chars),
            "superseded": bool(cor), "corrected_by": cor,
        })
    steps.sort(key=lambda s: (s["valid_from"] or "", rank.get(s["stage"], 9)))
    present = [s for s in _REASONING_ORDER if any(x["stage"] == s for x in steps)]
    missing = [s for s in _REASONING_ORDER if s not in present]
    return {"session": session_id, "steps": steps,
            "stages_present": present, "stages_missing": missing, "count": len(steps)}


def lessons_learned(events: List[AetherEvent], as_of: Optional[datetime] = None,
                    chars: Optional[int] = None,
                    source_prefix: Optional[str] = None,
                    k: Optional[int] = 20, standing_k: Optional[int] = 20,
                    superseded_k: Optional[int] = 5) -> Dict[str, Any]:
    """Lecons tirees des CORRECTIONS (C3) : ce qui a ete revise/abandonne, et la verite courante.
    PUR, LECTURE SEULE. Une lecon = une correction + les faits anterieurs de SA session qu'elle
    perime. `still_standing` = les decisions encore valides (non corrigees). Cite ses preuves.
    Vide tant qu'aucune correction n'est journalisee (calibre sur l'observe, pas invente).

    Economie de SORTIE (calibree sur le reel : lessons() debordait a ~80 Ko / 44 lecons +
    94 verites sur le journal central multi-projets) : `source_prefix` restreint a un projet ;
    `k` plafonne les lecons (les plus recentes d'abord), `standing_k` les verites debout,
    `superseded_k` les preuves citees PAR lecon (les plus proches de la correction d'abord).
    None = tout. Rien n'est cache en silence : `counts` reste COMPLET (avant plafonds),
    `truncated` signale la coupe, `superseded_count` garde le total par lecon."""
    asof = _aware(as_of) or datetime.now(timezone.utc)
    floor = datetime.min.replace(tzinfo=timezone.utc)
    k = None if k is None else max(0, k)
    standing_k = None if standing_k is None else max(0, standing_k)
    superseded_k = None if superseded_k is None else max(0, superseded_k)

    def valid(e: AetherEvent) -> bool:
        vf = _aware(e.valid_from)
        if vf and vf > asof:
            return False
        vt = _aware(e.valid_to)
        return not (vt and vt < asof)

    closes_idx = _closes_index(events, as_of=asof)   # clotures CIBLEES (curation)
    corrections = sorted(
        [e for e in events
         if e.type == EventType.CORRECTION and valid(e)
         and project_matches(e.data, e.source, source_prefix)
         and not _closed_by(closes_idx, e.id)],      # une correction close (doublon) sort
        key=lambda e: _aware(e.valid_from) or floor)

    lessons = []
    for c in corrections:
        sid = c.data.get("session_id")
        cvf = _aware(c.valid_from) or floor
        superseded = sorted(
            [e for e in events
             if sid is not None and e.data.get("session_id") == sid
             and e.type in _FACT_TYPES and (_aware(e.valid_from) or floor) < cvf],
            key=lambda e: _aware(e.valid_from) or floor,
            reverse=True) if sid is not None else []     # les plus proches de la correction d'abord
        lessons.append({
            "session": sid,
            "when": (cvf.isoformat() if c.valid_from else None),
            "source": c.source,
            "correction": _coupe(_text(c), 300, chars),   # la verite courante / le « pourquoi »
            "superseded_count": len(superseded),   # total AVANT plafond (rien de cache)
            "superseded": [                        # ce qui a ete revise / abandonne (borne)
                {"id": e.id, "type": e.type.value, "text": _coupe(_text(e), 200, chars)}
                for e in superseded[:superseded_k]],
        })

    # Deduplication de la SORTIE : une meme correction (session + texte) ne compte qu'une fois
    # (la plus recente). Le journal append-only garde, lui, tous les doublons (C3 intacte).
    by_key: Dict[Any, Dict[str, Any]] = {}
    for L in lessons:
        by_key[(L["session"], _norm(L["correction"]))] = L     # le plus recent ecrase
    lessons = sorted(by_key.values(), key=lambda L: L["when"] or "", reverse=True)
    n_lessons = len(lessons)                       # compte COMPLET, avant plafond

    corr_idx = _corrections_index(events)
    standing_all = [
        e for e in events
        if e.type == EventType.DECISION and valid(e)
        and project_matches(e.data, e.source, source_prefix)
        and not _superseded_by(corr_idx, e.data.get("session_id"), _aware(e.valid_from))
        and not _closed_by(closes_idx, e.id)         # une decision close ne tient plus debout
    ]
    standing_all.sort(key=lambda e: _aware(e.valid_from) or floor, reverse=True)
    still_standing = [
        {"id": e.id, "type": e.type.value, "session": e.data.get("session_id"),
         "valid_from": (_aware(e.valid_from).isoformat() if e.valid_from else None),
         "text": _coupe(_text(e), 200, chars)}
        for e in standing_all[:standing_k]
    ]
    return {
        "lessons": lessons[:k],
        "still_standing": still_standing,
        "counts": {"lessons": n_lessons, "still_standing": len(standing_all)},
        "truncated": bool((k is not None and n_lessons > k)
                          or (standing_k is not None and len(standing_all) > standing_k)),
    }


def project_review(events: List[AetherEvent], project: str, days: Optional[int] = None,
                   chars: Optional[int] = None,
                   now: Optional[datetime] = None, k: Optional[int] = 20) -> Dict[str, Any]:
    """Vue composee de revue de PROJET (par `source`), bi-temporelle, LECTURE SEULE, PURE.

    Reconstruit l'etat d'un projet depuis la SEULE memoire : decisions encore valides /
    corrigees (C3), hypotheses refutees / debout, validations, lecons. Signal de correction
    RAFFINE (calibrage 06/07) : une correction supersede le SEUL fait immediatement anterieur de
    sa session (+ clotures ciblees `data.closes` / `valid_to`), pas TOUS les faits de la session —
    ce qui evite l'inflation observee. `corrected_by` = le « pourquoi ca a change ». Les `lecons`
    reutilisent `lessons_learned` (vue « pourquoi », signal large). Ne juge pas : signaux dates et
    sources, l'humain tranche. `days` = activite des N derniers jours (None = tout). Sortie bornee
    (economie de sortie) : `counts` COMPLET, `truncated` signale la coupe."""
    asof = _aware(now) or datetime.now(timezone.utc)
    floor = datetime.min.replace(tzinfo=timezone.utc)
    kk = None if k is None else max(0, k)
    pool = events
    if days is not None:
        cutoff = asof - timedelta(days=days)
        pool = [e for e in events if (_aware(e.valid_from) or floor) >= cutoff]

    closes_idx = _closes_index(pool, as_of=asof)

    def valid(e: AetherEvent) -> bool:
        vf = _aware(e.valid_from)
        if vf and vf > asof:
            return False
        vt = _aware(e.valid_to)
        return not (vt and vt < asof)

    def brief(e: AetherEvent, extra: Optional[dict] = None) -> Dict[str, Any]:
        vf = _aware(e.valid_from)
        d = {"id": e.id, "type": e.type.value, "session": e.data.get("session_id"),
             "valid_from": vf.isoformat() if vf else None, "text": _coupe(_text(e), 200, chars),
             **_structure(e)}
        if extra:
            d.update(extra)
        return d

    def by_recent(items):
        return sorted(items, key=lambda e: _aware(e.valid_from) or floor, reverse=True)

    mine = [e for e in pool if project_matches(e.data, e.source, project)]

    # --- Correction RAFFINEE (calibrage 06/07) : une correction (valide a asof) supersede le SEUL
    # fait IMMEDIATEMENT anterieur de SA session (le « dernier etat dit »), pas TOUS les faits.
    # Corrige l'inflation observee (bureau : session dense en decisions + 1 correction tardive
    # flaguait TOUT). Les clotures ciblees (data.closes) et valid_to restent precises.
    _FACT = {EventType.DECISION, EventType.HYPOTHESIS, EventType.NOTE,
             EventType.OBSERVATION, EventType.VALIDATION}
    facts_by_sid: Dict[Any, list] = {}
    corr_by_sid: Dict[Any, list] = {}
    for e in mine:
        sid = e.data.get("session_id")
        if e.type == EventType.CORRECTION:
            if valid(e):
                corr_by_sid.setdefault(sid, []).append(e)
        elif e.type in _FACT:
            facts_by_sid.setdefault(sid, []).append(e)
    corrected: Dict[str, List[str]] = {}
    for sid, corrs in corr_by_sid.items():
        facts = sorted(facts_by_sid.get(sid, []), key=lambda e: _aware(e.valid_from) or floor)
        for c in corrs:
            cvf = _aware(c.valid_from) or floor
            pred = None
            for f in facts:                             # le dernier fait STRICTEMENT anterieur
                if (_aware(f.valid_from) or floor) < cvf:
                    pred = f
                else:
                    break
            if pred is not None:
                corrected.setdefault(pred.id, []).append(c.id)

    def _closed(e: AetherEvent) -> bool:
        vt = _aware(e.valid_to)
        return bool(vt and vt <= asof)

    def corrected_by(e: AetherEvent) -> List[str]:      # correction immediate + clotures ciblees
        return corrected.get(e.id, []) + _closed_by(closes_idx, e.id)

    def is_corrected(e: AetherEvent) -> bool:
        return bool(corrected_by(e) or _closed(e))

    ll = lessons_learned(pool, as_of=asof, source_prefix=project, k=kk, standing_k=kk)  # lecons

    decs = [e for e in mine if e.type == EventType.DECISION]
    dec_val = by_recent([e for e in decs if valid(e) and not is_corrected(e)])
    dec_corr = by_recent([e for e in decs if is_corrected(e)])
    hyp = [e for e in mine if e.type == EventType.HYPOTHESIS]
    hyp_ref = by_recent([e for e in hyp if is_corrected(e)])
    hyp_std = by_recent([e for e in hyp if valid(e) and not is_corrected(e)])
    vals = by_recent([e for e in mine if e.type == EventType.VALIDATION and valid(e) and not is_corrected(e)])

    counts = {"decisions_valides": len(dec_val), "decisions_corrigees": len(dec_corr),
              "hypotheses_refutees": len(hyp_ref), "hypotheses_debout": len(hyp_std),
              "validations": len(vals), "lecons": ll["counts"]["lessons"]}
    truncated = bool(ll["truncated"] or (kk is not None and any(
        n > kk for n in (len(dec_val), len(dec_corr), len(hyp_ref), len(hyp_std), len(vals)))))
    return {
        "project": project, "as_of": asof.isoformat(), "params": {"days": days, "k": k},
        "counts": counts, "truncated": truncated,
        "decisions_valides": [brief(e) for e in dec_val][:kk],
        "decisions_corrigees": [brief(e, {"corrected_by": corrected_by(e)}) for e in dec_corr][:kk],
        "hypotheses_refutees": [brief(e, {"corrected_by": corrected_by(e)}) for e in hyp_ref][:kk],
        "hypotheses_debout": [brief(e) for e in hyp_std][:kk],
        "validations": [brief(e) for e in vals][:kk],
        "lecons": ll["lessons"],
    }


def pitfalls(events: List[AetherEvent], source_prefix: Optional[str] = None,
             actifs_seuls: bool = False, k: Optional[int] = 20,
             chars: Optional[int] = None, as_of: Optional[datetime] = None) -> Dict[str, Any]:
    """Les PIEGES connus — ce qui a deja coute une erreur. PUR, LECTURE SEULE.

    Pourquoi un outil dedie : pour un agent sans continuite, refaire deux fois la meme erreur est
    LE defaut structurel. Un avertissement noye dans un pave narratif ne protege personne.

    Plus RECENT d'abord (un piege recent porte sur l'etat courant du systeme). C3 tenu : un piege
    revise reste lisible AVEC son drapeau `superseded` et son `corrected_by` — on ne supprime
    jamais, on signale. `actifs_seuls=True` ne garde que ce qui mord encore (usage : la reprise).
    Sortie bornee (`k`), `counts` COMPLET, `truncated` signale la coupe."""
    asof = _aware(as_of) or datetime.now(timezone.utc)
    closes_idx = _closes_index(events, as_of=asof)
    floor = datetime.min.replace(tzinfo=timezone.utc)

    retenus = []
    for e in events:
        if e.type != EventType.PITFALL:
            continue
        if not project_matches(e.data, e.source, source_prefix):
            continue
        vf = _aware(e.valid_from)
        if vf and vf > asof:
            continue                                  # pas encore valide (bi-temporel)
        # Un piege n'est perime que par une cloture CIBLEE (`data.closes`) ou un `valid_to`.
        # Le supersede session+temps, lui, vise les fils de raisonnement : applique aux pieges il
        # ferait disparaitre un avertissement encore valable des qu'une correction SANS RAPPORT
        # tombe dans la meme session (constat 25/07). Un garde-fou ne se perime pas par voisinage.
        corrected = _closed_by(closes_idx, e.id)
        vt = _aware(e.valid_to)
        clos = bool(vt and vt <= asof)
        if actifs_seuls and (corrected or clos):
            continue
        retenus.append((e, corrected, clos))

    retenus.sort(key=lambda t: (_aware(t[0].valid_from) or floor), reverse=True)
    total = len(retenus)
    kk = total if k is None else max(0, k)
    items = [{
        "id": e.id, "source": e.source, "session": e.data.get("session_id"),
        "valid_from": (_aware(e.valid_from).isoformat() if e.valid_from else None),
        "text": _coupe(_text(e), 300, chars),
        "superseded": bool(corrected or clos), "corrected_by": corrected,
    } for e, corrected, clos in retenus[:kk]]
    return {"as_of": asof.isoformat(), "counts": {"pieges": total},
            "truncated": total > kk, "pieges": items}


def resume(events: List[AetherEvent], project: str, days: Optional[int] = 14,
           k: int = 5, chars: Optional[int] = None, index: Optional[Dict[str, Any]] = None,
           curation: Optional[Dict[str, Any]] = None,
           now: Optional[datetime] = None) -> Dict[str, Any]:
    """REPRENDRE un projet en UN appel. PUR, LECTURE SEULE, borne.

    Pourquoi : reprendre exigeait d'enchainer health + recent + brief + recall + project_review,
    plus les fichiers du depot — une dizaine d'aller-retours avant la premiere ligne utile
    (constat d'usage du 24/07/2026). Toutes les briques existaient ; il manquait la COMPOSITION.

    L'ORDRE fait la valeur — une vue de reprise est une hierarchie d'attention, pas un dump :
      1. `pieges`    ce qui a deja coute une erreur (actifs seuls)
      2. `sante`     les angles morts du substrat lui-meme
      3. `etat`      ou en est le projet (decisions valides/corrigees, validations)
      4. `recent`    ce qui a bouge dans la fenetre
      5. `revisions` ce qui a CHANGE d'avis, avec le pourquoi (C3)

    Ne devine rien, ne juge rien : compose l'observe, chaque element date et source."""
    asof = _aware(now) or datetime.now(timezone.utc)
    pieges = pitfalls(events, source_prefix=project, actifs_seuls=True, k=k, chars=chars,
                      as_of=asof)
    sante = health(events, index=index, curation=curation, now=asof)
    cur = _vue_curation(curation, k)
    # V3 : les desaccords entre agents. Un desaccord qui n'arrive jamais sous les yeux n'est
    # pas arbitre : il pourrit. C'est le seul endroit ou l'humain peut trancher (C1).
    trancher = contradictions_ouvertes(events, source_prefix=project, as_of_=asof)[:max(0, k)]
    etat = project_review(events, project, days=days, k=k, chars=chars, now=asof)
    dernier = recent(events, days=days or 3650, source_prefix=project, limit=k, now=asof,
                     chars=chars)
    lecons = lessons_learned(events, as_of=asof, source_prefix=project, k=k, standing_k=0,
                             chars=chars)
    return {
        "projet": project,
        "as_of": asof.isoformat(),
        "fenetre_jours": days,
        "pieges": pieges["pieges"],
        "sante": {"degraded": sante["degraded"], "warnings": sante["warnings"],
                  "event_count": sante["event_count"], "last_event_at": sante["last_event_at"]},
        "etat": {"counts": etat["counts"],
                 "decisions_valides": etat["decisions_valides"],
                 "decisions_corrigees": etat["decisions_corrigees"]},
        "recent": dernier["latest"][:max(0, k)],      # `recent` borne decisions/corrections, pas `latest`
        "revisions": lecons["lessons"],
        "curation": cur,
        "a_trancher": trancher,
        "counts": {"pieges": pieges["counts"]["pieges"], "revisions": lecons["counts"]["lessons"],
                   "a_decider": cur["en_attente"], "a_trancher": len(trancher)},
    }


CURATION_PERIMEE_JOURS = 3          # au-dela, le diagnostic decrit une memoire qui n'existe plus


def _vue_curation(curation: Optional[Dict[str, Any]], k: int) -> Dict[str, Any]:
    """Ce qui attend une DECISION (propositions, avec leur commande d'approbation) et ce qui
    attend un JUGEMENT (signalements). PUR.

    Les distinguer n'est pas cosmetique : 43 quasi-doublons ne sont pas 43 actions. Les confondre
    fait paraitre la file enorme et decourage — c'est ainsi qu'une boucle de curation s'arrete."""
    c = curation or {}
    counts = c.get("counts") or {}
    a_juger = sum(v for cle, v in counts.items()
                  if cle in ("near_duplicates", "stale_candidates",
                             "contradiction_candidates", "placeholder_facts"))
    props = list(c.get("proposals") or [])[:max(0, k)]
    return {"en_attente": counts.get("proposals", 0), "a_juger": a_juger,
            "calcule_le": c.get("as_of"), "propositions": props}


QUESTIONS_CLOTURE = (
    "Qu'as-tu APPRIS que le depot ne dit pas ? (une phrase, --kind decision)",
    "Un PIEGE a-t-il coute plus de dix minutes ? (--kind pitfall : c'est ce qui sert le plus)",
    "Une decision anterieure est-elle a REVISER ? (--kind correction --closes <id>)",
)


def contrat_cloture(events: List[AetherEvent], project: str, k: int = 3,
                    curation: Optional[Dict[str, Any]] = None,
                    now: Optional[datetime] = None) -> Dict[str, Any]:
    """Fin de session : ce qu'il faut RETENIR, et ce qui attend une DECISION. PUR, LECTURE SEULE.

    V4 (25/07/2026). A l'ouverture `resume` dit les cinq choses a savoir ; il manquait le pendant.
    Un agent laisse libre ecrit trop, ou oublie — constat direct sur mes propres entrees.

    Second volet (proposition Wilfred) : PRESENTER les validations en attente pour que l'humain
    tranche. C1 n'est pas contourne, il devient APPLICABLE — un arbitrage qu'on ne presente jamais
    n'est pas un arbitrage, c'est un blocage.

    Le risque n'est pas que l'agent decide, c'est l'APPROBATION EN LOT : montrer 43 propositions
    et obtenir un « ok » respecte C1 dans la forme et le vide dans les faits. D'ou : peu a la fois
    (`k`), le contenu EXACT de ce qui serait clos, et la REVERSIBILITE affichee — une cloture C3
    se clot a son tour, rien n'est detruit, une erreur d'arbitrage se repare."""
    asof = _aware(now) or datetime.now(timezone.utc)
    a_decider: List[Dict[str, Any]] = []

    props = list((curation or {}).get("proposals") or [])
    for p in props:
        a_decider.append({
            "type": "curation", "action": p.get("action"),
            "pourquoi": p.get("rationale"),
            "vise": p.get("targets"), "conserve": p.get("keep"),
            "command": p.get("command"), "command_reject": p.get("command_reject"),
            # Une cloture C3 se clot a son tour : l'arbitrage est REPARABLE.
            "reversible": True,
        })

    for c in contradictions_ouvertes(events, source_prefix=project, as_of_=asof):
        a_decider.append({
            "type": "contradiction",
            "pourquoi": "%s contredit ce fait de %s" % (", ".join(c["contredit_par"]), c["source"]),
            "vise": [c["id"]], "texte": c["text"],
            "command": ('memlog-http "<votre arbitrage>" --kind correction '
                        '--session arbitrages --closes %s' % c["id"]),
            "reversible": True,
        })

    total = len(a_decider)
    kk = max(0, k)
    return {
        "projet": project, "as_of": asof.isoformat(),
        "questions": list(QUESTIONS_CLOTURE),
        "a_decider": a_decider[:kk],
        "counts": {"a_decider": total},     # compteur HONNETE meme quand la liste est coupee
        "truncated": total > kk,
        "note": ("Presente, jamais applique : l'humain tranche (C1). Toute cloture est "
                 "reversible (C3) — on clot, on ne supprime jamais."),
    }


SILENCE_ALERTE_JOURS = 7            # au-dela, une memoire qui ne recoit plus rien est un symptome


def health(events: List[AetherEvent], index: Optional[Dict[str, Any]] = None,
           curation: Optional[Dict[str, Any]] = None,
           now: Optional[datetime] = None) -> Dict[str, Any]:
    """Sante du substrat memoire (kit LLM universel), LECTURE SEULE, PURE. On a pu lire -> disponible ;
    on renvoie le nombre d'evenements, la date du dernier, le nombre de sources distinctes. Sert la
    REPRISE (health -> recent -> recall) sans rien deviner. La latence/reseau releve du connecteur.

    ANGLES MORTS (24/07/2026) : `available: true` ne suffit pas. Le canal semantique a tourne mort
    (0 vecteur sur 2518) pendant que `health` affichait tout vert — il fallait penser a interroger
    `index_status`. Une memoire doit annoncer ce qu'elle NE sait pas : `index` (sortie de
    `index_coverage`) alimente `warnings` + `degraded`. Champs historiques inchanges."""
    n = _aware(now) or datetime.now(timezone.utc)
    last: Optional[datetime] = None
    sources: set = set()
    for e in events:
        vf = _aware(e.valid_from)
        if vf and (last is None or vf > last):
            last = vf
        if e.source:
            sources.add(e.source)

    avertissements = avertissements_sante(last, bool(events), index, n, curation)
    return {"available": True, "event_count": len(events),
            "last_event_at": last.isoformat() if last else None, "sources": len(sources),
            "degraded": bool(avertissements), "warnings": avertissements}


def avertissements_sante(last: Optional[datetime], a_des_events: bool,
                         index: Optional[Dict[str, Any]], now: datetime,
                         curation: Optional[Dict[str, Any]] = None) -> List[str]:
    """Angles morts du substrat, en clair. PUR. UNE seule source de verite : `health` (pur) et
    `projection.health_sql` l'appellent tous deux — un oracle a deja pris en defaut une version
    dupliquee (24/07)."""
    out: List[str] = []
    if index:
        elig, idx = index.get("eligible", 0), index.get("indexed", 0)
        if elig and not idx:
            out.append("index semantique VIDE (0/%d) : recall_semantic se replie sur le lexical"
                       % elig)
        elif elig and not index.get("fresh", True):
            out.append("index semantique partiel (%d/%d, %.1f%%) : recall_semantic ne voit pas tout"
                       % (idx, elig, index.get("covered_pct", 0.0)))
    if last is not None:
        jours = (now - last).days
        if jours >= SILENCE_ALERTE_JOURS:
            out.append("dernier evenement il y a %d jours : la capture est peut-etre interrompue"
                       % jours)
    elif a_des_events:
        out.append("aucun evenement date : impossible de juger la fraicheur")
    if curation:
        calcule = curation.get("as_of")
        try:
            age = (now - _aware(datetime.fromisoformat(calcule))).days if calcule else None
        except (TypeError, ValueError):
            age = None
        if age is not None and age >= CURATION_PERIMEE_JOURS:
            out.append("diagnostic de curation vieux de %d jours : il decrit une memoire qui "
                       "n'existe plus" % age)
    return out


def reuse_stats(events: List[AetherEvent], as_of: Optional[datetime] = None) -> Dict[str, Any]:
    """Instrumentation LECTURE SEULE : combien de tours ont ete SERVIS depuis la memoire (cache,
    sans rappeler le modele) et combien de tokens d'entree epargnes. Mesure la reutilisation/valeur
    de la memoire, a partir des marqueurs deja journalises a la capture (`served_from`,
    `cached_tokens`, `saved_input_tokens`). PUR. Il MESURE l'observe — ne predit, ne juge rien.
    (Etape 3 Memory Intelligence : on accumule le signal ; obsolescence/confiance viendront APRES.)"""
    asof = _aware(as_of) or datetime.now(timezone.utc)
    turns = served = saved_cache = saved_window = 0
    by_source: Dict[str, int] = {}
    for e in events:
        if e.type != EventType.TOKEN_USAGE:
            continue
        vf = _aware(e.valid_from)
        if vf and vf > asof:
            continue
        vt = _aware(e.valid_to)
        if vt and vt < asof:
            continue
        turns += 1
        d = e.data
        sf = d.get("served_from")
        if sf:
            served += 1
            by_source[sf] = by_source.get(sf, 0) + 1
            saved_cache += int(d.get("cached_tokens", 0) or 0)
        saved_window += int(d.get("saved_input_tokens", 0) or 0)
    return {
        "turns": turns,
        "served_from_memory": served,
        "served_pct": round(100 * served / turns, 1) if turns else 0.0,
        "by_source": by_source,
        "input_tokens_saved_by_cache": saved_cache,
        "input_tokens_saved_by_windowing": saved_window,
    }


def briefing_today(events: List[AetherEvent], now: Optional[datetime] = None) -> Dict[str, Any]:
    """Briefing d'usage du jour (lecture seule). Reutilise economy/inspect."""
    from .inspect import summarize
    from .economy import usage_digest
    now = _aware(now) or datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    todays = [e for e in events
              if (_aware(e.valid_from) or now).strftime("%Y-%m-%d") == today]
    digest = usage_digest(summarize(todays))
    return {
        "date": today,
        "turns": digest["totals"]["turns"],
        "input_tokens": digest["totals"]["in"],
        "output_tokens": digest["totals"]["out"],
        "compaction_saved": digest.get("compaction_saved", 0),
        "by_model": {f"{m}|{cs}": b for (m, cs), b in digest["by_basis"].items()},
    }


# Types reellement indexes (garder en phase avec index._TEXT_TYPES).
_INDEXABLE_TYPES = {EventType.PROMPT, EventType.COMPLETION,
                    EventType.CORRECTION, EventType.TOOL_RESULT,
                    EventType.DECISION, EventType.NOTE,
                    EventType.HYPOTHESIS, EventType.OBSERVATION, EventType.VALIDATION}


def index_coverage(events: List[AetherEvent], vecs: Dict[str, Any],
                   as_of: Optional[datetime] = None, type_: Optional[str] = None,
                   source_prefix: Optional[str] = None) -> Dict[str, Any]:
    """Fraicheur de l'index semantique : part des evenements INDEXABLES (types textuels, texte
    non vide, valides a as_of, filtres) couverts par l'index d'embeddings. PUR, LECTURE SEULE.
    `fresh`=True si tout l'eligible est indexe ; sinon recall_semantic ne voit pas tout (partiel)."""
    asof = _aware(as_of) or datetime.now(timezone.utc)
    eligible = indexed = 0
    for e in events:
        if e.type not in _INDEXABLE_TYPES:           # seuls ces types sont embeddes (cf. index.py)
            continue
        if type_ and e.type.value != type_:
            continue
        if not _source_matches(e.source, source_prefix):
            continue
        vf = _aware(e.valid_from)
        if vf and vf > asof:
            continue
        vt = _aware(e.valid_to)
        if vt and vt < asof:
            continue
        if not (e.data.get("text") or e.description or "").strip():   # non indexable (pas de texte)
            continue
        eligible += 1
        if e.id in vecs:
            indexed += 1
    missing = eligible - indexed
    pct = round(100 * indexed / eligible, 1) if eligible else 100.0
    return {"eligible": eligible, "indexed": indexed, "missing": missing,
            "covered_pct": pct, "fresh": missing == 0}


def recall_semantic(events: List[AetherEvent], query: str, embedder, store,
                    as_of: Optional[datetime] = None, k: int = 10,
                    type_: Optional[str] = None, source_prefix: Optional[str] = None,
                    explain: bool = False, min_fused: float = 0.0,
                    sem_weight: float = 0.5,
                    qvec: Optional[List[float]] = None) -> List[Dict[str, Any]]:
    """Recall HYBRIDE = CANAL N.2 (ne remplace pas le lexical). Porte bi-temporelle (C3)
    decisionnelle, puis FUSION 50/50 de la couverture lexicale [0,1] et du cosinus semantique.
    'min_fused' = plancher de pertinence (etouffe le bruit). 'explain' detaille les scores.
    'qvec' (opt) = embedding de la requete deja calcule (evite une 2e passe d'embedder).
    Repli lexical si pas d'index. LECTURE SEULE."""
    from .semantic import cosine
    asof = _aware(as_of) or datetime.now(timezone.utc)
    corr_idx = _corrections_index(events)            # C3 : fraicheur (correction posterieure ?)
    closes_idx = _closes_index(events, as_of=asof)   # clotures CIBLEES (curation)
    # On filtre AVANT de reclamer des vecteurs : la memoire consommee suit le nombre de
    # CANDIDATS, pas la taille du corpus (mesure 24/07 : charger tout l'index coutait 0,79 s
    # et l'integralite des float32 en RAM). `vectors_for` = lecture ciblee ; un store sans
    # cette methode (EmbeddingStore jsonl, store tiers) reste servi par `load()`.
    eligibles = []
    for e in events:
        if type_ and e.type.value != type_:
            continue
        if not project_matches(e.data, e.source, source_prefix):
            continue
        vf = _aware(e.valid_from)
        if vf and vf > asof:
            continue
        vt = _aware(e.valid_to)
        if vt and vt < asof:
            continue
        eligibles.append(e)
    cible = getattr(store, "vectors_for", None)
    vecs = cible([e.id for e in eligibles]) if callable(cible) else store.load()
    cand = [(e, vecs[e.id]) for e in eligibles if e.id in vecs]
    if not cand:                                         # pas d'index -> repli lexical pur
        return recall(events, query, as_of=as_of, k=k, type_=type_, source_prefix=source_prefix)
    if qvec is None:
        qvec = embedder.embed([query])[0]
    hits = []
    for e, vec in cand:
        sem_n = max(0.0, cosine(qvec, vec))
        lex = _score(query, _text(e))                    # couverture, deja [0,1]
        sw = min(1.0, max(0.0, sem_weight))
        fused = round(sw * sem_n + (1.0 - sw) * lex, 4)
        if fused < min_fused:                            # plancher : on etouffe le bruit
            continue
        corrected = (_superseded_by(corr_idx, e.data.get("session_id"), _aware(e.valid_from))
                     + _closed_by(closes_idx, e.id))
        h = {
            "id": e.id, "type": e.type.value, "source": e.source,
            "valid_from": (_aware(e.valid_from).isoformat() if e.valid_from else None),
            "turn_id": e.data.get("turn_id"), "session_id": e.data.get("session_id"),
            "fused": fused, "semantic": round(sem_n, 4), "lexical": round(lex, 4),
            "text": _snippet(_text(e), query),
            "superseded": bool(corrected), "corrected_by": corrected,
            **_structure(e),
        }
        if explain:
            h["semantic_norm"] = round(sem_n, 4)
            h["lexical_norm"] = round(lex, 4)
        hits.append(h)
    hits.sort(key=lambda h: (h["fused"], h["valid_from"] or ""), reverse=True)
    return hits[:k]
