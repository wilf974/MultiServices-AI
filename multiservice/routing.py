"""Tranche 1 - Router mince : choisit local/cloud via policy.decide, execute le backend choisi,
et capture la PROVENANCE explicite dans les events. La decision reste VISIBLE (RouteResult +
events) ; JAMAIS cachee dans un backend opaque (anti-pattern RoutingBackend rejete).

Effets isoles ici (appel backend) ; la decision (policy) et la construction d'events (router) sont
PURES. Le Router ne sait que router ; il ne mute pas le journal (le caller persiste les events).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from . import policy
from .backends import Backend, BackendError, Completion
from .events import AetherEvent
from .router import events_for_turn


@dataclass
class RouteResult:
    completion: Completion
    events: List[AetherEvent]
    decision: policy.RoutingDecision


class Router:
    """Tient un backend local (obligatoire) + un backend cloud (optionnel). `route_turn` decide,
    execute, et renvoie reponse + events portant la provenance. Defaut local : sans cloud, tout
    reste local."""

    def __init__(self, local: Backend, cloud: Optional[Backend] = None) -> None:
        self.local = local
        self.cloud = cloud

    def generate(self, prompt: str, cloud_ok: bool = False,
                 sent: Optional[List[dict]] = None, on_token=None):
        """Decide (policy) -> execute le backend choisi -> repli LOCAL si le cloud echoue
        (BackendError : cle absente, HTTP, reseau). JAMAIS de crash opaque. `sent` (messages
        composes) sert au backend si fourni, sinon [{user: prompt}] ; streaming via on_token.
        La decision reste VISIBLE (provenance retournee). Retourne (completion, count_source, provenance)."""
        decision = policy.decide(prompt, cloud_ok=cloud_ok, has_cloud=self.cloud is not None)
        msgs = sent if sent is not None else [{"role": "user", "content": prompt}]
        prov = {
            "routed_to": decision.route,
            "routing_reason": decision.reason,
            "sensitivity_reasons": list(decision.sensitivity.reasons),
            "cloud_ok": cloud_ok,
            "has_cloud": self.cloud is not None,
        }
        if decision.route == "cloud":
            try:
                completion = self.cloud.chat(msgs, on_token=on_token)   # effet de bord (cloud)
                return completion, self.cloud.count_source, prov
            except BackendError as e:                    # cloud KO -> repli local explicite
                prov = {**prov, "routed_to": "local",
                        "routing_reason": "cloud_error_fallback_local", "cloud_error": e.kind}
        completion = self.local.chat(msgs, on_token=on_token)           # defaut / fallback LOCAL
        return completion, self.local.count_source, prov

    def route_turn(
        self,
        prompt: str,
        cloud_ok: bool = False,
        session_id: Optional[str] = None,
        user_source: str = "user:local",
        now: Optional[datetime] = None,
    ) -> RouteResult:
        """Tour complet (capture incluse) pour l'usage simple. S'appuie sur generate() puis
        construit les events avec provenance. La decision est la VISEE initiale (la provenance
        des events reflete, elle, le service reel, fallback inclus)."""
        completion, count_source, provenance = self.generate(prompt, cloud_ok=cloud_ok)
        events = events_for_turn(
            prompt, completion, count_source,
            session_id=session_id, user_source=user_source, now=now, routing=provenance,
        )
        decision = policy.decide(prompt, cloud_ok=cloud_ok, has_cloud=self.cloud is not None)
        return RouteResult(completion=completion, events=events, decision=decision)
