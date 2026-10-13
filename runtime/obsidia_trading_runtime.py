"""
ObsidiaTradingRuntime — facade produit stable (P1-D).

Assemble la chaine Native deja existante et l'expose via une surface
publique minimale : `build`, `status`, `run_cycle`, `get_receipt`,
`history`, `replay`. Ne reimplemente RIEN de cette chaine — ne recalcule ni
agents, ni consensus, ni Strategy, ni Sizing, ni Authority. `run_cycle()`
delegue exactement une fois a `CycleEngine.run_cycle()`.

Le Reference Runtime construit ici utilise TOUJOURS :
  - `RealKX108Client` (jamais un client de test) ;
  - `ProofPolicy.REQUIRED` ;
  - `NativeReferenceStrategy` / `NativeReferenceSizing` ;
  - `execution.binder.paper_execution.build_paper_cycle_engine` (PAPER only).

Aucun import de `apps/cockpit*` ici : ce module est la couche que le Cockpit
devra a l'avenir consommer, jamais l'inverse.
"""
from __future__ import annotations

from typing import Optional, Sequence

from domain.calibration import CalibrationPack
from execution.binder.engine import CycleEngine, CycleOutcome
from execution.binder.paper_execution import build_paper_cycle_engine
from execution.binder.proof_policy import ProofPolicy
from governance.bridge.kx108_client import RealKX108Client
from native.agents.adapter import ROSTER_17, NativeRosterAnalysisAdapter
from native.agents.aggregation import NativeRosterAggregation
from native.agents.calibrated_agents import build_calibrated_trading_agents
from native.sizing.native_reference_sizing import NativeReferenceSizing
from native.strategy.native_consensus_strategy import NativeReferenceStrategy
from proof.receipts.receipt_store import ReceiptStore, StoredCycleReceipt
from proof.receipts.replay import AuditReplayResult, ReplayEngine

from runtime.config import RuntimeConfig
from runtime.status import (
    AgentsStatus,
    BinderStatus,
    CalibrationStatus,
    KX108Status,
    MarketStatus,
    ModeStatus,
    ProofStatus,
    ReceiptStoreStatus,
    ReplayStatus,
    RuntimeStatus,
    SizingStatus,
    StrategyStatus,
)


class ReplayUnavailable(RuntimeError):
    """Aucun ReceiptStore configure sur ce runtime : rien a rejouer honnetement."""


class ObsidiaTradingRuntime:
    """
    Facade produit du Reference Runtime OBSIDIA_TRADING.

    Ne contient aucune intelligence de trading. Toute decision, tout
    dimensionnement, toute autorite restent la responsabilite exclusive des
    composants assembles par `build()`.
    """

    def __init__(
        self,
        *,
        engine: CycleEngine,
        config: RuntimeConfig,
        receipt_store: Optional[ReceiptStore],
        replay_engine: Optional[ReplayEngine],
    ) -> None:
        self._engine = engine
        self._config = config
        self._receipt_store = receipt_store
        self._replay_engine = replay_engine
        self._agents_status = (
            AgentsStatus.NATIVE_17_CALIBRATED
            if config.calibration_pack is not None
            else AgentsStatus.NATIVE_17
        )
        self._calibration_status = (
            CalibrationStatus.CONFIGURED
            if config.calibration_pack is not None
            else CalibrationStatus.NOT_CONFIGURED
        )
        self._sizing_status = (
            SizingStatus.CONFIGURED
            if config.sizing_policy is not None
            else SizingStatus.NOT_CONFIGURED
        )
        self._receipt_store_status = (
            ReceiptStoreStatus.CONFIGURED
            if receipt_store is not None
            else ReceiptStoreStatus.UNAVAILABLE
        )
        self._replay_status = (
            ReplayStatus.AVAILABLE if replay_engine is not None else ReplayStatus.UNAVAILABLE
        )
        # Etat observe uniquement par evidence reelle de cycle (F/L) — jamais
        # promu a la construction. Ne peut regresser que sur une evidence
        # d'echec reelle (fail_closed), jamais sur une simple absence
        # d'evidence (ex: cycle d'abstention qui n'a jamais appele KX108).
        self._kx108_status = KX108Status.REAL_CLIENT_CONFIGURED
        self._last_outcome: Optional[CycleOutcome] = None

    # ── Construction ─────────────────────────────────────────────────────

    @classmethod
    def build(cls, config: RuntimeConfig) -> "ObsidiaTradingRuntime":
        """
        Assemble le Reference Runtime a partir d'une configuration explicite.

        Reutilise, sans les reimplementer :
          - `RealKX108Client` (jamais `FixtureKX108Client`/`StaticKX108Client`) ;
          - `NativeRosterAnalysisAdapter` + `NativeRosterAggregation`
            (roster standard, ou calibre via `build_calibrated_trading_agents`
            si `config.calibration_pack` est fourni) ;
          - `NativeReferenceStrategy` / `NativeReferenceSizing(config.sizing_policy)` ;
          - `ReceiptStore(config.receipt_store_path)` si fourni, sinon `None`
            (le cycle reste chaine en memoire, comme `CycleEngine` le fait
            deja sans port de preuve) ;
          - `build_paper_cycle_engine` sous `ProofPolicy.REQUIRED`.

        Une configuration invalide echoue ICI, jamais silencieusement au
        premier `run_cycle()`.
        """
        kx108_client = RealKX108Client(base_url=config.kernel_url)

        if config.calibration_pack is not None:
            agent_instances = build_calibrated_trading_agents(config.calibration_pack)
        else:
            agent_instances = [cls_ for cls_ in ROSTER_17]

        analysis = NativeRosterAnalysisAdapter(agent_instances)
        aggregation = NativeRosterAggregation()
        strategy = NativeReferenceStrategy()
        sizing = NativeReferenceSizing(config.sizing_policy)

        receipt_store: Optional[ReceiptStore] = (
            ReceiptStore(config.receipt_store_path)
            if config.receipt_store_path is not None
            else None
        )
        replay_engine: Optional[ReplayEngine] = (
            ReplayEngine(receipt_store) if receipt_store is not None else None
        )

        engine = build_paper_cycle_engine(
            analysis=analysis,
            aggregation=aggregation,
            kx108_client=kx108_client,
            symbols=config.symbols,
            order_ledger_path=config.order_ledger_path,
            strategy=strategy,
            sizing=sizing,
            proof=receipt_store,
            proof_policy=ProofPolicy.REQUIRED,
        )

        return cls(
            engine=engine,
            config=config,
            receipt_store=receipt_store,
            replay_engine=replay_engine,
        )

    # ── Surface publique ─────────────────────────────────────────────────

    def status(self) -> RuntimeStatus:
        """Photographie en lecture seule de l'etat du runtime, par sous-systeme."""
        return RuntimeStatus(
            market=self._market_status(),
            agents=self._agents_status,
            calibration=self._calibration_status,
            strategy=StrategyStatus.NATIVE_REFERENCE,
            sizing=self._sizing_status,
            kx108=self._kx108_status,
            binder=BinderStatus.ACTIVE,
            mode=ModeStatus.PAPER,
            proof=ProofStatus.REQUIRED,
            receipt_store=self._receipt_store_status,
            replay=self._replay_status,
        )

    def run_cycle(self) -> CycleOutcome:
        """
        Delegue exactement une fois a `CycleEngine.run_cycle()`.

        Ne recalcule rien : agents, consensus, Strategy, Sizing et Authority
        restent entierement produits par les composants assembles dans
        `build()`. Met a jour l'evidence observee de statut (KX108/market)
        a partir du `CycleOutcome` reellement retourne, jamais devinee.
        """
        outcome = self._engine.run_cycle()
        self._last_outcome = outcome
        self._update_kx108_status(outcome)
        return outcome

    def get_receipt(self, cycle_id: str) -> Optional[StoredCycleReceipt]:
        """
        Retourne le receipt persiste pour `cycle_id`, ou `None` si absent ou
        si aucun `ReceiptStore` n'est configure sur ce runtime.
        """
        if self._receipt_store is None:
            return None
        return self._receipt_store.find_by_cycle_id(cycle_id)

    def history(self, limit: int = 100) -> Sequence[StoredCycleReceipt]:
        """
        Receipts persistes les plus recents, dans l'ordre d'ecriture.

        Retourne un tuple vide si aucun `ReceiptStore` n'est configure —
        jamais un index parallele invente.
        """
        if self._receipt_store is None:
            return ()
        return self._receipt_store.history(limit)

    def replay(self, cycle_id: str) -> AuditReplayResult:
        """
        Reconstruction en lecture seule d'un cycle prouve — sans effet de
        bord, jamais un appel broker ni Binder. Delegue a
        `ReplayEngine.replay_audit`.
        """
        if self._replay_engine is None:
            raise ReplayUnavailable(
                "aucun ReceiptStore configure sur ce runtime : rien a rejouer "
                "(RuntimeConfig.receipt_store_path est absent)."
            )
        return self._replay_engine.replay_audit(cycle_id)

    # ── Internes ─────────────────────────────────────────────────────────

    def _market_status(self) -> MarketStatus:
        if self._last_outcome is None:
            return MarketStatus.NOT_OBSERVED
        state = self._last_outcome.state
        if state.degraded_reasons:
            return MarketStatus.DEGRADED
        if state.market:
            return MarketStatus.OBSERVED
        return MarketStatus.DEGRADED

    def _update_kx108_status(self, outcome: CycleOutcome) -> None:
        """
        Promeut/retrograde l'etat KX108 uniquement sur evidence reelle.

        - Aucune `Decision` (ex: cycle d'abstention avant tout appel a
          l'autorite) : aucune evidence, statut inchange.
        - `metrics["fail_closed"]` present : le client reel a echoue ou le
          Kernel a repondu invalide -> UNAVAILABLE.
        - `metrics["kx108_response"]["source"] == "KX108_REAL"` : round-trip
          reel confirme -> REAL_OBSERVED.
        - Sinon (decision presente mais sans evidence exploitable) : statut
          inchange, jamais devine.
        """
        decision = outcome.decision
        if decision is None:
            return
        metrics = decision.metrics or {}
        if metrics.get("fail_closed"):
            self._kx108_status = KX108Status.UNAVAILABLE
            return
        response = metrics.get("kx108_response")
        if isinstance(response, dict) and response.get("source") == "KX108_REAL":
            self._kx108_status = KX108Status.REAL_OBSERVED
