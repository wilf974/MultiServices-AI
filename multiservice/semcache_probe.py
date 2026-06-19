"""Sprint 18 - sonde de CALIBRATION du cache semantique (lecture seule, sortie ASCII).

But : decider le seuil du cache semantique SUR LE REEL, pas a l'aveugle. On embed les prompts
utilisateur du journal, on mesure la distribution des cosinus entre paires, et on compte combien
de QUASI-DOUBLONS existent a divers seuils. Verite usage-driven :
  - s'il existe des paires >= 0.95 -> le cache mordrait (utile), le seuil les separe du bruit ;
  - s'il n'y en a aucune -> le cache ne servirait jamais sur ces donnees (honnete : on le dit).

Ne mute rien. Embedding 100% local (Ollama). Lancer : python -m multiservice.semcache_probe
"""
from __future__ import annotations

from typing import List, Tuple

from . import config
from .journal import read_events
from .semantic import OllamaEmbedder, cosine

THRESHOLDS = [0.99, 0.97, 0.95, 0.93, 0.90, 0.85]


def _user_prompts(events) -> List[Tuple[str, str]]:
    """(id, texte) des prompts utilisateur non vides, dedupliques par texte normalise."""
    seen = set()
    out = []
    for e in events:
        if e.type.value != "prompt":
            continue
        if not (e.source or "").startswith("user"):
            continue
        txt = (e.data.get("text") or e.description or "").strip()
        key = txt.lower()
        if len(txt) < 8 or key in seen:
            continue
        seen.add(key)
        out.append((e.id, txt))
    return out


def main() -> None:
    events = read_events(config.JOURNAL_PATH)
    prompts = _user_prompts(events)
    n = len(prompts)
    print("[semcache-probe] prompts utilisateur distincts : %d" % n)
    if n < 2:
        print("[semcache-probe] trop peu de prompts pour mesurer une repetition.")
        return

    embedder = OllamaEmbedder(model=config.EMBED_MODEL, host=config.OLLAMA_HOST)
    vecs = embedder.embed([t for _, t in prompts])
    print("[semcache-probe] embeddings calcules : %d (modele=%s)" % (len(vecs), config.EMBED_MODEL))

    pairs = []  # (sim, i, j)
    for i in range(n):
        for j in range(i + 1, n):
            pairs.append((cosine(vecs[i], vecs[j]), i, j))
    pairs.sort(reverse=True)

    sims = [p[0] for p in pairs]
    mx = max(sims); avg = sum(sims) / len(sims)
    print("[semcache-probe] paires=%d  cos_max=%.3f  cos_moyen=%.3f" % (len(pairs), mx, avg))
    print("[semcache-probe] quasi-doublons par seuil (paires distinctes) :")
    for th in THRESHOLDS:
        c = sum(1 for s in sims if s >= th)
        print("    seuil >= %.2f : %d paire(s)" % (th, c))

    print("[semcache-probe] top 5 paires les plus proches :")
    for s, i, j in pairs[:5]:
        a = prompts[i][1][:60].replace("\n", " ")
        b = prompts[j][1][:60].replace("\n", " ")
        print("    cos=%.3f" % s)
        print("       A: %s" % a)
        print("       B: %s" % b)

    fire = sum(1 for s in sims if s >= 0.95)
    print("[semcache-probe] VERDICT : au seuil conservateur 0.95, le cache aurait mordu "
          "sur %d paire(s)." % fire)
    if fire == 0:
        print("[semcache-probe] -> sur ces donnees, pas de repetition quasi-identique : "
              "le cache ne servirait pas encore. Sa valeur viendra des questions recurrentes "
              "dans le temps / entre sessions (FAQ d'agent). Garder le seuil haut.")


if __name__ == "__main__":
    main()
