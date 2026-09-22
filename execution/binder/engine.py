"""
Obsidia Trading — moteur de cycle.

C'est ici que vit la boucle. Streamlit n'en est plus proprietaire : il
affiche un etat et envoie des commandes, rien de plus.

Le cycle, tel que defini par le chantier :

    observe -> analyse -> agrege -> propose -> dimensionne -> DECIDE (X-108)
            -> planifie -> execute -> prouve -> surveille -> reevalue
                                                                  |
                                                                  v
                                                        nouvel etat du monde

Invariants tenus par ce module, et verifies par les tests :

  1. Aucun ordre ne part sans Authority.ACT. La barriere est appliquee deux
     fois : le planner ne fabrique pas de plan, et le bridge refuse tout plan
     non autorise.
  2. ACT, HOLD et BLOCK produisent tous un receipt.
  3. Le moteur n'importe rien de Streamlit, ni d'aucune UI.
  4. Meme etat et meme horloge produisent la meme decision et le meme hash.
  5. (F11) Un cycle ne pretend jamais a une preuve qu'il n'a pas. Si la
     persistance du receipt echoue apres que le broker ait potentiellement
     accepte un ordre, `CycleOutcome.proof_outcome` porte
     EXECUTION_SUCCEEDED_PROOF_INCOMPLETE — jamais un succes silencieux,
     jamais un faux echec. Sous `ProofPolicy.REQUIRED`, un port de preuve
     injoignable AVANT tout appel broker bloque l'execution elle-meme (voir
     execution/binder/proof_policy.py). Proof != authority : cette regle ne
     change jamais qui decide (KX108) ni qui execute (Binder).
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from domain.market import MarketSnapshot
from domain.order_ledger import OrderLedgerEvent, OrderLedgerEventType
from domain.orders import ExecutionPlan, ExecutionResult
from domain.portfolio import PortfolioState
from domain.proposal import (
    ActionProposal,
    AgentOutput,
    Consensus,
    Opportunity,
    SizingDecision,
    StrategyCandidate,
)
from domain.receipt import GENESIS_HASH, CycleReceipt, Decision
from domain.state import TradingDomainState
from domain.types import ActionKind, Authority, Mode
from domain.ports.broker import BrokerPort, BrokerUnavailable, UnauthorizedExecution
from domain.ports.clock import ClockPort, SystemClock
from domain.ports.market_data import MarketDataPort, MarketDataUnavailable
from domain.ports.order_ledger import OrderLedgerPort
from execution.binder.contracts import (
    AggregationPort,
    AnalysisPort,
    AuthorityPort,
    DiscoveryPort,
    PlannerPort,
    SizingPort,
    StrategyPort,
)
from execution.binder.proof_policy import ProofOutcome, ProofPolicy

logger = logging.getLogger("obsidia.runtime")


@dataclass
class CycleOutcome:
    """
    Tout ce qu'un cycle a produit.

    Objet unique remis a l'appelant — cockpit, script, test. L'UI n'a jamais
    besoin de rien d'autre pour se peindre.
    """

    cycle_id: str
    state: TradingDomainState
    receipt: Optional[CycleReceipt] = None
    decision: Optional[Decision] = None
    proposal: Optional[ActionProposal] = None
    plan: Optional[ExecutionPlan] = None
    execution: Optional[ExecutionResult] = None
    agent_outputs: Sequence[AgentOutput] = field(default_factory=tuple)
    opportunities: Sequence[Opportunity] = field(default_factory=tuple)
    strategies: Sequence[StrategyCandidate] = field(default_factory=tuple)
    events: List[str] = field(default_factory=list)
    error: Optional[str] = None
    proof_outcome: ProofOutcome = ProofOutcome.NOT_APPLICABLE

    @property
    def authority(self) -> Optional[Authority]:
        return self.decision.authority if self.decision else None

    @property
    def touched_the_market(self) -> bool:
        return bool(self.execution and self.execution.touched_the_market)

    def as_dict(self) -> dict:
        return {
            "cycle_id": self.cycle_id,
            "authority": self.authority.value if self.authority else None,
            "state": self.state.as_dict(),
            "decision": self.decision.as_dict() if self.decision else None,
            "plan": self.plan.as_dict() if self.plan else None,
            "execution": self.execution.as_dict() if self.execution else None,
            "receipt": self.receipt.as_dict() if self.receipt else None,
            "opportunities": [o.as_dict() for o in self.opportunities],
            "strategies": [s.as_dict() for s in self.strategies],
            "events": list(self.events),
            "touched_the_market": self.touched_the_market,
            "error": self.error,
            "proof_outcome": self.proof_outcome.value,
        }


class RealKernelRequiresProofRequired(RuntimeError):
    """
    F12.1 — Le Reference Runtime (vrai Kernel X-108 + gouvernance + Binder)
    ne doit jamais se construire silencieusement sous ProofPolicy.BEST_EFFORT.

    ProofPolicy.BEST_EFFORT reste disponible ailleurs (tests, demo, chemins
    explicitement non critiques) : c'est le defaut historique, et il n'est
    pas retire. Cette exception ne bloque qu'un seul cas precis : un
    `CycleEngine` construit avec une autorite qui appelle reellement le
    Kernel reel (`RealKX108Client`, F12) sans que l'appelant n'ait choisi
    explicitement `ProofPolicy.REQUIRED`. Le correctif est toujours du cote
    de l'appelant : passer `proof_policy=ProofPolicy.REQUIRED`.
    """


def _reject_implicit_best_effort_with_real_kernel(
    authority: AuthorityPort, proof_policy: ProofPolicy
) -> None:
    """
    Garde-fou F12.1, par construction plutot que par convention.

    Import local (jamais au niveau module) : `execution/binder/engine.py`
    reste decouple de `governance/bridge/` — n'importe quelle implementation
    de `AuthorityPort` peut etre injectee sans que ce module en connaisse la
    nature. On introspecte ici uniquement pour refuser une combinaison
    dangereuse, jamais pour dependre structurellement de KX108GovernanceBridge.
    """
    if proof_policy is not ProofPolicy.BEST_EFFORT:
        return
    try:
        from governance.bridge.governance_bridge import KX108GovernanceBridge
        from governance.bridge.kx108_client import RealKX108Client
    except ImportError:  # pragma: no cover - governance/bridge toujours present ici
        return
    if isinstance(authority, KX108GovernanceBridge) and isinstance(
        authority.client, RealKX108Client
    ):
        raise RealKernelRequiresProofRequired(
            "RealKX108Client (vrai Kernel X-108) ne peut pas etre associe a "
            "ProofPolicy.BEST_EFFORT : le chemin gouverne critique exige "
            "ProofPolicy.REQUIRED. Passez proof_policy=ProofPolicy.REQUIRED "
            "explicitement a CycleEngine (ou a build_paper_cycle_engine)."
        )


class CycleEngine:
    """
    Orchestrateur du cycle decisionnel.

    Ne contient aucune intelligence propre : il enchaine des etapes fournies
    par injection et fait respecter les invariants de gouvernance entre elles.
    Remplacer les agents, l'autorite ou le broker ne demande pas de le
    modifier.
    """

    def __init__(
        self,
        *,
        market_data: MarketDataPort,
        broker: BrokerPort,
        analysis: AnalysisPort,
        aggregation: AggregationPort,
        authority: AuthorityPort,
        symbols: Sequence[str],
        mode: Mode = Mode.SIM,
        clock: Optional[ClockPort] = None,
        discovery: Optional[DiscoveryPort] = None,
        strategy: Optional[StrategyPort] = None,
        sizing: Optional[SizingPort] = None,
        planner: Optional[PlannerPort] = None,
        proof: Optional[Any] = None,
        proof_policy: ProofPolicy = ProofPolicy.BEST_EFFORT,
        order_ledger: Optional[OrderLedgerPort] = None,
        advance_world: Optional[Any] = None,
    ) -> None:
        self.market_data = market_data
        self.broker = broker
        self.analysis = analysis
        self.aggregation = aggregation
        self.authority = authority
        self.symbols = list(symbols)
        self.mode = mode
        self.clock: ClockPort = clock or SystemClock()
        self.discovery = discovery
        self.strategy = strategy
        self.sizing = sizing
        self.planner = planner
        self.proof = proof
        self.proof_policy = proof_policy
        self.order_ledger = order_ledger
        _reject_implicit_best_effort_with_real_kernel(authority, proof_policy)
        # Fait progresser le monde d'un pas avant l'observation. Separer
        # « le monde avance » de « on l'observe » evite que lire un etat
        # le modifie — defaut central de ui/app.py, ou se redessiner
        # faisait avancer le marche et produisait une decision.
        self.advance_world = advance_world

        self.cycle_count = 0
        self._last_receipt_hash = (
            proof.last_hash() if proof is not None else GENESIS_HASH
        )

    # ─────────────────────────────────────────────────────────────────────
    # Cycle complet
    # ─────────────────────────────────────────────────────────────────────

    def run_cycle(self) -> CycleOutcome:
        """
        Execute un cycle complet et retourne tout ce qu'il a produit.

        Ne leve jamais : une panne devient une degradation constatee, portee
        par l'etat et le receipt (chantier §30). Un cycle qui echoue reste un
        cycle observable.
        """
        self.cycle_count += 1
        cycle_id = f"c{self.cycle_count:06d}-{uuid.uuid4().hex[:8]}"
        events: List[str] = []

        def note(message: str) -> None:
            events.append(message)
            logger.info("[%s] %s", cycle_id, message)

        note("cycle started")

        # ── 0. Laisser le monde avancer ───────────────────────────────────
        if self.advance_world is not None:
            try:
                self.advance_world()
            except Exception as exc:  # noqa: BLE001
                note(f"progression du monde impossible: {exc}")

        # ── 1. Observer ───────────────────────────────────────────────────
        try:
            state = self._observe(cycle_id, note)
        except Exception as exc:  # noqa: BLE001 - un cycle ne doit jamais tuer le moteur
            logger.exception("[%s] observation impossible", cycle_id)
            empty = TradingDomainState(
                cycle_id=cycle_id,
                observed_at=self.clock.now(),
                mode=self.mode,
                degraded_reasons=(f"observation impossible: {exc}",),
            )
            return CycleOutcome(
                cycle_id=cycle_id, state=empty, events=events, error=str(exc)
            )

        # ── 2. Decouvrir ──────────────────────────────────────────────────
        opportunities = self._discover(state, note)
        if opportunities:
            state = state.with_opportunities(tuple(opportunities))

        symbol = self._select_symbol(opportunities)
        snapshot = state.snapshot(symbol) if symbol else None
        if symbol is None or snapshot is None:
            note("aucun instrument observable : cycle sans proposition")
            decision = self._abstain(
                cycle_id, "aucun instrument observable dans l'etat courant"
            )
            receipt, proof_outcome = self._prove(
                cycle_id, state, decision, None, None, note, opportunities, ()
            )
            return CycleOutcome(
                cycle_id=cycle_id,
                state=state,
                decision=decision,
                proposal=decision.proposal,
                receipt=receipt,
                opportunities=tuple(opportunities),
                events=events,
                proof_outcome=proof_outcome,
            )

        # ── 3. Analyser et agreger ────────────────────────────────────────
        outputs = tuple(self.analysis.analyse(symbol, snapshot, state.portfolio))
        note(f"agents executed ({len(outputs)} signaux sur {symbol})")
        consensus = self.aggregation.aggregate(outputs)
        note(f"consensus {consensus.side} conf={consensus.confidence:.3f}")

        # ── 4. Envisager, comparer, dimensionner ──────────────────────────
        strategies = self._build_strategies(
            symbol, snapshot, consensus, state, opportunities, note
        )
        selected, rejected = self._select_strategy(strategies)
        sizing = self._size(selected, snapshot, state.portfolio, note)

        proposal = ActionProposal(
            symbol=symbol,
            action=selected.action if selected else self._action_from(consensus),
            consensus=consensus,
            sizing=sizing,
            selected_strategy=selected,
            rejected_strategies=tuple(rejected),
            agent_outputs=outputs,
            opportunity=next((o for o in opportunities if o.symbol == symbol), None),
            rationale=selected.rationale if selected else "proposition issue du consensus",
            portfolio_context=state.portfolio.risk_metrics() if state.portfolio else {},
        )
        note(f"proposal {proposal.action.value} qty={sizing.quantity:g}")

        # ── 5. DECIDER — seule etape portant une autorite ─────────────────
        decision_id = f"d{self.cycle_count:06d}-{uuid.uuid4().hex[:8]}"
        decision = self.authority.evaluate(proposal, state, decision_id)
        note(f"X108 decision {decision.authority.value} — {decision.reason}")

        # ── 6. Planifier ──────────────────────────────────────────────────
        plan = self._plan(decision, state, note)

        # ── 7. Executer ───────────────────────────────────────────────────
        execution = self._execute(cycle_id, decision, plan, note)

        # ── 8. Prouver ────────────────────────────────────────────────────
        receipt, proof_outcome = self._prove(
            cycle_id, state, decision, plan, execution, note, opportunities, strategies
        )

        note("cycle completed")
        return CycleOutcome(
            cycle_id=cycle_id,
            state=state,
            receipt=receipt,
            decision=decision,
            proposal=proposal,
            plan=plan,
            execution=execution,
            agent_outputs=outputs,
            opportunities=tuple(opportunities),
            strategies=tuple(strategies),
            events=events,
            proof_outcome=proof_outcome,
        )

    # ─────────────────────────────────────────────────────────────────────
    # Etapes
    # ─────────────────────────────────────────────────────────────────────

    def _observe(self, cycle_id: str, note) -> TradingDomainState:
        """Construit l'etat du domaine a partir du marche et du broker."""
        degraded: List[str] = []

        market: Dict[str, MarketSnapshot] = {}
        try:
            market = dict(self.market_data.snapshots(self.symbols))
            note(f"market state acquired ({len(market)}/{len(self.symbols)} symboles)")
        except MarketDataUnavailable as exc:
            degraded.append(f"donnees de marche indisponibles: {exc}")
            note(f"market feed unavailable: {exc}")

        for missing in (s for s in self.symbols if s not in market):
            degraded.append(f"aucune donnee pour {missing}")

        portfolio: Optional[PortfolioState] = None
        try:
            portfolio = self.broker.portfolio()
            note("portfolio state acquired")
        except BrokerUnavailable as exc:
            degraded.append(f"broker indisponible: {exc}")
            note(f"broker unavailable: {exc}")

        context = None
        try:
            context = self.market_data.context()
        except Exception as exc:  # noqa: BLE001 - le contexte est facultatif
            degraded.append(f"contexte indisponible: {exc}")

        return TradingDomainState(
            cycle_id=cycle_id,
            observed_at=self.clock.now(),
            mode=self.mode,
            market=market,
            portfolio=portfolio,
            context=context,
            degraded_reasons=tuple(degraded),
        )

    def _discover(self, state: TradingDomainState, note) -> List[Opportunity]:
        if self.discovery is None:
            return []
        try:
            found = list(self.discovery.discover(state))
        except Exception as exc:  # noqa: BLE001
            note(f"discovery failed: {exc}")
            return []
        note(f"opportunities generated ({len(found)})")
        return found

    def _select_symbol(self, opportunities: Sequence[Opportunity]) -> Optional[str]:
        """Le meilleur candidat decouvert, a defaut le premier symbole suivi."""
        if opportunities:
            ordered = sorted(
                opportunities,
                key=lambda o: (
                    {"VALID": 0, "CONFLICTED": 1, "WEAK": 2, "DEGRADED": 3}.get(o.status, 9),
                    -o.score,
                    o.symbol,
                    o.opportunity_id,
                ),
            )
            return ordered[0].symbol
        if self.discovery is not None:
            return None
        return self.symbols[0] if self.symbols else None

    def _build_strategies(
        self,
        symbol: str,
        snapshot: MarketSnapshot,
        consensus: Consensus,
        state: TradingDomainState,
        opportunities: Sequence[Opportunity],
        note,
    ) -> List[StrategyCandidate]:
        if self.strategy is None:
            return []
        try:
            built = list(
                self.strategy.build(
                    symbol, snapshot, consensus, state.portfolio, opportunities
                )
            )
        except Exception as exc:  # noqa: BLE001
            note(f"strategy generation failed: {exc}")
            return []
        note(f"strategy generated ({len(built)} candidate(s))")
        return built

    @staticmethod
    def _select_strategy(candidates: Sequence[StrategyCandidate]):
        """Retient la candidate la plus confiante ; les autres sont conservees."""
        if not candidates:
            return None, []
        ordered = sorted(
            candidates,
            key=lambda c: (
                {"VALID": 0, "CONFLICTED": 1, "WEAK": 2, "INCOMPATIBLE": 3}.get(c.status, 9),
                -c.confidence,
                c.strategy_id,
            ),
        )
        return ordered[0], list(ordered[1:])

    def _size(
        self,
        candidate: Optional[StrategyCandidate],
        snapshot: MarketSnapshot,
        portfolio: Optional[PortfolioState],
        note,
    ) -> SizingDecision:
        if candidate is None or self.sizing is None:
            return SizingDecision(
                quantity=0.0,
                requested_quantity=0.0,
                capped_by=("aucune_strategie",),
                rationale="aucune strategie retenue : rien a dimensionner",
            )
        decision = self.sizing.size(candidate, snapshot, portfolio)
        if decision.is_refused:
            note(f"sizing refused: {decision.rationale}")
        elif decision.was_reduced:
            note(f"sizing reduced: {decision.rationale}")
        return decision

    def _plan(
        self, decision: Decision, state: TradingDomainState, note
    ) -> Optional[ExecutionPlan]:
        if self.planner is None:
            return None
        if not decision.authorizes_action:
            note(f"aucun plan : autorite {decision.authority.value}")
            return None
        plan = self.planner.plan(decision, state)
        if plan is None:
            note("aucun plan : action non executable en l'etat")
        else:
            note(f"execution planned {plan.side.value} {plan.quantity:g} {plan.symbol}")
        return plan

    def _execute(
        self,
        cycle_id: str,
        decision: Decision,
        plan: Optional[ExecutionPlan],
        note,
    ) -> Optional[ExecutionResult]:
        """
        Envoie le plan au broker.

        Deuxieme barriere de gouvernance : meme si un plan arrivait ici sans
        autorite — erreur de cablage, appelant fautif — il serait refuse avant
        tout contact avec l'exterieur.
        """
        if plan is None:
            return None

        if not decision.authorizes_action or not plan.is_authorized:
            note(f"execution refusee : autorite {decision.authority.value}")
            result = ExecutionResult.not_submitted(
                plan, f"autorite insuffisante ({decision.authority.value})"
            )
            self._record_ledger_result(cycle_id, result, note)
            return result

        if self.proof_policy is ProofPolicy.REQUIRED and self.proof is not None:
            # F11 : seule difference comportementale de REQUIRED. On ne
            # demarre pas une action irreversible en sachant deja que le
            # port de preuve est injoignable. Une lecture legere
            # (last_hash, jamais une ecriture) suffit a verifier qu'il
            # repond avant tout contact broker.
            try:
                self.proof.last_hash()
            except Exception as exc:  # noqa: BLE001
                reason = f"preuve indisponible avant execution (PROOF_REQUIRED): {exc}"
                note(f"execution refusee : {reason}")
                result = ExecutionResult.not_submitted(plan, reason)
                self._record_ledger_result(cycle_id, result, note)
                return result

        if self.order_ledger is not None:
            blocker = self.order_ledger.submission_blocker(plan)
            if blocker:
                reason = f"garde idempotence: {blocker}"
                note(f"execution refusee : {reason}")
                return ExecutionResult.not_submitted(plan, reason)
            try:
                self.order_ledger.append(
                    OrderLedgerEvent.from_plan(
                        event_type=OrderLedgerEventType.SUBMISSION_INTENT_RECORDED,
                        cycle_id=cycle_id,
                        plan=plan,
                        timestamp=self.clock.now(),
                        mode=self.mode,
                    )
                )
                note("order intent persisted before broker submit")
            except Exception as exc:  # noqa: BLE001
                reason = f"intention non persistable ({exc})"
                note(f"execution refusee : {reason}")
                return ExecutionResult.not_submitted(plan, reason)

        try:
            result = self.broker.submit(plan)
        except UnauthorizedExecution as exc:
            note(f"execution refusee par le bridge : {exc}")
            result = ExecutionResult.not_submitted(plan, str(exc))
            self._record_ledger_result(cycle_id, result, note)
            return result
        except BrokerUnavailable as exc:
            note(f"broker unavailable a la soumission : {exc}")
            result = ExecutionResult.not_submitted(plan, f"broker indisponible: {exc}")
            self._record_ledger_result(cycle_id, result, note)
            return result
        except Exception as exc:  # noqa: BLE001
            logger.exception("echec de soumission")
            result = ExecutionResult.not_submitted(plan, f"echec de soumission: {exc}")
            self._record_ledger_result(cycle_id, result, note)
            return result

        note(
            f"order submitted status={result.status.value} "
            f"id={result.broker_order_id} filled={result.filled_quantity:g}"
        )
        self._record_ledger_result(cycle_id, result, note)
        return result

    def _record_ledger_result(
        self,
        cycle_id: str,
        result: ExecutionResult,
        note,
        receipt_hash: Optional[str] = None,
    ) -> None:
        if self.order_ledger is None:
            return
        try:
            self.order_ledger.append(
                OrderLedgerEvent.from_result(
                    cycle_id=cycle_id,
                    result=result,
                    timestamp=self.clock.now(),
                    mode=self.mode,
                    receipt_hash=receipt_hash,
                )
            )
        except ValueError as exc:
            note(f"ledger duplicate ignored: {exc}")
        except Exception as exc:  # noqa: BLE001
            note(f"ledger result persistence failed: {exc}")

    def _prove(
        self,
        cycle_id: str,
        state: TradingDomainState,
        decision: Decision,
        plan: Optional[ExecutionPlan],
        execution: Optional[ExecutionResult],
        note,
        opportunities: Sequence[Opportunity] = (),
        strategies: Sequence[StrategyCandidate] = (),
    ) -> tuple[CycleReceipt, ProofOutcome]:
        """Emet le receipt du cycle. Toujours, quelle que soit l'autorite."""
        extensions = {
            "pass6": {
                "opportunities": [o.as_dict() for o in opportunities],
                "strategy_candidates": [s.as_dict() for s in strategies],
                "sizing": decision.proposal.sizing.as_dict(),
                "proposal": decision.proposal.as_dict(),
            },
            "pass7": {
                "decision_id": decision.decision_id,
                "execution_plan_id": plan.causal_id if plan else None,
                "external_order_id": execution.broker_order_id if execution else None,
                "execution_status": execution.lifecycle_status if execution else None,
                "fills": [f.as_dict() for f in execution.fills] if execution else [],
                "position_before": state.portfolio.as_dict() if state.portfolio else None,
                "position_after": None,
                "monitoring_observations": [],
                "position_reviews": [],
                "reevaluation_proposals": [],
            }
        }

        receipt = CycleReceipt(
            cycle_id=cycle_id,
            decision_id=decision.decision_id,
            recorded_at=self.clock.now(),
            mode=self.mode,
            state_fingerprint=state.fingerprint(),
            decision=decision,
            previous_receipt_hash=self._last_receipt_hash,
            execution_plan=plan,
            execution_result=execution,
            consequence=self._consequence(execution),
            degraded_reasons=state.degraded_reasons,
            extensions=extensions,
        )
        # Le hash de chainage est celui que le port de preuve a reellement
        # conserve : un decorateur (extension ERC-8004, par exemple) peut
        # enrichir le receipt avant stockage, et c'est cette version enrichie
        # qui fait foi. Se fier au receipt local romprait la chaine.
        #
        # F11 : si l'ecriture echoue, on ne fait PAS comme si de rien
        # n'etait. Deux consequences distinctes, jamais confondues :
        #   1. `_last_receipt_hash` n'avance PAS sur un receipt jamais
        #      persiste — sinon le PROCHAIN receipt reellement ecrit
        #      chainerait sur un hash absent du store, et
        #      `verify_chain`/`ReceiptChainVerifier` signalerait une
        #      rupture qui n'existait pas avant cet echec (le store
        #      resterait valide jusqu'au dernier receipt REELLEMENT ecrit).
        #   2. l'appelant recoit un `proof_outcome` honnete : jamais
        #      "rien ne s'est passe", jamais "echec d'execution", quand le
        #      broker a pu accepter l'ordre malgre l'echec de preuve.
        if self.proof is None:
            proof_outcome = ProofOutcome.NOT_APPLICABLE
            digest = receipt.decision_hash()
            self._last_receipt_hash = digest
        else:
            try:
                persisted = self.proof.record(receipt)
                receipt = persisted or receipt
                digest = receipt.decision_hash()
                self._last_receipt_hash = digest
                proof_outcome = ProofOutcome.PROVEN
            except Exception as exc:  # noqa: BLE001
                note(f"echec d'ecriture de la preuve: {exc}")
                if execution is not None and execution.touched_the_market:
                    proof_outcome = ProofOutcome.EXECUTION_SUCCEEDED_PROOF_INCOMPLETE
                    note(
                        "ATTENTION: le broker a pu accepter l'ordre mais le receipt "
                        "final n'a pas pu etre persiste durablement — issue reelle "
                        "inconnue tant que la preuve n'est pas reconstituee"
                    )
                else:
                    proof_outcome = ProofOutcome.ABSTENTION_PROOF_INCOMPLETE
                digest = receipt.decision_hash()
                # _last_receipt_hash volontairement NON modifie : voir note ci-dessus.

        note(f"receipt finalized {digest[:12]} proof={proof_outcome.value}")
        return receipt, proof_outcome

    @staticmethod
    def _consequence(execution: Optional[ExecutionResult]) -> Dict[str, Any]:
        """Ce qui est effectivement arrive, tel qu'on peut le constater."""
        if execution is None:
            return {"executed": False, "reason": "aucune execution pour ce cycle"}
        return {
            "executed": execution.submitted,
            "status": execution.status.value,
            "broker_order_id": execution.broker_order_id,
            "filled_quantity": execution.filled_quantity,
            "average_fill_price": execution.average_fill_price,
            "is_partial": execution.is_partial,
            "rejected_reason": execution.rejected_reason,
        }

    def _abstain(self, cycle_id: str, reason: str) -> Decision:
        """Decision d'abstention quand le cycle ne peut rien proposer."""
        proposal = ActionProposal(
            symbol="",
            action=ActionKind.NO_ACTION,
            consensus=Consensus(side="HOLD", confidence=0.0),
            sizing=SizingDecision(
                quantity=0.0, requested_quantity=0.0, capped_by=("aucune_proposition",)
            ),
            rationale=reason,
        )
        return Decision(
            decision_id=f"d{self.cycle_count:06d}-abstain",
            authority=Authority.HOLD,
            reason=reason,
            proposal=proposal,
        )

    @staticmethod
    def _action_from(consensus: Consensus) -> ActionKind:
        """Repli quand aucune strategie n'est fournie : lecture directe du consensus."""
        return {
            "BUY": ActionKind.BUY,
            "SELL": ActionKind.SELL,
        }.get(consensus.side, ActionKind.WAIT)
