"""
Governance Bridge — pont vers KX108, PAS une recreation locale de KX108
(chantier F5).

Architecture imposee :

    Trading Domain (Agents / Simulation / Local signals)
        -> Canonical DomainState + TradeIntent (ActionProposal)
        -> Governance Bridge (ce module)
        -> KX108 (KX108Client)
        -> Canonical Decision (Authority ACT/HOLD/BLOCK)
        -> Binder (execution/binder/engine.py, deja existant)
        -> Execution

Le Governance Bridge implemente `AuthorityPort` (execution/binder/contracts.py)
et se branche dans `CycleEngine` exactement comme n'importe quelle autre
implementation de ce port — aucune modification du moteur n'est necessaire.

REGLES NON NEGOCIABLES (verifiees par tests/unit/test_governance_bridge.py) :
  1. Ce module prepare les entrees attendues par KX108 (ir_payload.py).
  2. Il preserve provenance/unknowns/contradictions/risk_flags/evidence dans
     le payload transmis (bloc "evidence"), meme si KX108 ne les consomme
     pas pour decider.
  3. Il appelle l'interface KX108Client — jamais un Kernel reimplemente ici.
  4. Il ne recupere QUE le verdict canonique (Authority) de la reponse.
  5. Il transmet uniquement ce verdict au Binder via Decision.authority —
     le score structurel local est attache a Decision.structural_score
     comme evidence, jamais comme source de l'autorite.
  6. Il ne recalcule ni ne substitue JAMAIS lui-meme la decision finale : le
     signal local ne peut pas produire ACT, ni transformer un HOLD/BLOCK
     renvoye par KX108 en ACT.
  7. Si KX108 est indisponible ou renvoie une reponse invalide -> FAIL
     CLOSED (Authority.HOLD), jamais ACT par defaut.
"""
from __future__ import annotations

from typing import Any, Dict

from domain.proposal import ActionProposal
from domain.receipt import Decision
from domain.state import TradingDomainState
from domain.types import Authority
from governance.bridge.ir_payload import build_trading_ir_payload
from governance.bridge.kx108_client import KX108Client, KX108Unavailable
from governance.bridge.local_signal import compute_local_structural_signal

_VALID_LEGACY_VERDICTS = {"ACT", "ALLOW", "HOLD", "BLOCK"}


class InvalidKX108Response(RuntimeError):
    """La reponse KX108 ne porte pas un verdict exploitable."""


class KX108GovernanceBridge:
    """
    Implementation de `AuthorityPort` (execution/binder/contracts.py) qui
    delegue la decision a un `KX108Client`.

    Ne PAS instancier avec `UnavailableKX108Client` en pensant obtenir un
    comportement "permissif" par defaut : c'est au contraire le chemin qui
    garantit le fail-closed (voir `evaluate`).
    """

    def __init__(self, client: KX108Client) -> None:
        self._client = client

    @property
    def client(self) -> KX108Client:
        """
        Expose le `KX108Client` injecte, en lecture seule (F12.1).

        Existe uniquement pour permettre a `CycleEngine` de verifier, par
        construction, qu'un `RealKX108Client` n'est jamais associe
        implicitement a `ProofPolicy.BEST_EFFORT` (voir
        execution/binder/engine.py). Ne sert a rien d'autre : le bridge
        reste la seule chose qui appelle ce client pour decider.
        """
        return self._client

    # ── AuthorityPort ───────────────────────────────────────────────────

    def evaluate(
        self,
        proposal: ActionProposal,
        state: TradingDomainState,
        decision_id: str,
    ) -> Decision:
        local_signal = compute_local_structural_signal(list(proposal.agent_outputs))
        ir_payload = build_trading_ir_payload(proposal, state, local_signal)

        try:
            response = self._client.evaluate_trading(ir_payload)
        except KX108Unavailable as exc:
            return self._fail_closed(
                decision_id, proposal, local_signal, ir_payload,
                reason=f"KX108 indisponible (fail-closed) : {exc}",
            )
        except Exception as exc:  # noqa: BLE001 - toute panne cote client = fail-closed
            return self._fail_closed(
                decision_id, proposal, local_signal, ir_payload,
                reason=f"KX108 a leve une exception inattendue (fail-closed) : {exc}",
            )

        try:
            authority = self._parse_authority(response)
        except InvalidKX108Response as exc:
            return self._fail_closed(
                decision_id, proposal, local_signal, ir_payload,
                reason=f"reponse KX108 invalide (fail-closed) : {exc}",
                kx108_response=response,
            )

        return Decision(
            decision_id=decision_id,
            authority=authority,
            reason=f"KX108 verdict={response.get('verdict')} (source=KX108_BRIDGE)",
            proposal=proposal,
            structural_score=local_signal.S,
            metrics={
                "ir_payload": ir_payload,
                "kx108_response": response,
                "local_signal": {
                    "T": local_signal.T,
                    "H": local_signal.H,
                    "A_norm": local_signal.A_norm,
                    "S": local_signal.S,
                    "n_agents": local_signal.n_agents,
                },
            },
        )

    # ── Internes ─────────────────────────────────────────────────────────

    @staticmethod
    def _parse_authority(response: Any) -> Authority:
        if not isinstance(response, dict):
            raise InvalidKX108Response(f"reponse non-dict recue: {type(response).__name__}")
        verdict = response.get("verdict")
        if not isinstance(verdict, str) or verdict.strip().upper() not in _VALID_LEGACY_VERDICTS:
            raise InvalidKX108Response(f"verdict absent ou inconnu: {verdict!r}")
        # Authority.from_legacy ne fait AUCUNE substitution silencieuse :
        # ACT/ALLOW->ACT, HOLD->HOLD, BLOCK->BLOCK, tout le reste leve deja
        # une ValueError plus haut via la verification ci-dessus.
        return Authority.from_legacy(verdict)

    @staticmethod
    def _fail_closed(
        decision_id: str,
        proposal: ActionProposal,
        local_signal,
        ir_payload: Dict[str, Any],
        *,
        reason: str,
        kx108_response: Any = None,
    ) -> Decision:
        """
        Fail-closed : Authority.HOLD, jamais ACT. Le signal local est
        toujours attache comme evidence (structural_score), jamais comme
        justification d'une autorite qu'il n'a pas le droit de produire.
        """
        return Decision(
            decision_id=decision_id,
            authority=Authority.HOLD,
            reason=reason,
            proposal=proposal,
            structural_score=local_signal.S,
            metrics={
                "ir_payload": ir_payload,
                "kx108_response": kx108_response,
                "fail_closed": True,
            },
        )
