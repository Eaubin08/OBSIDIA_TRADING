"""
apps/cockpit_v2/reference_runtime_view.py — Cockpit V2 Phase A.

Assemble et exécute un cycle réel via les composants déjà prouvés :
RealKX108Client (F12) -> KX108GovernanceBridge (F5) -> CycleEngine (F3/F6)
-> ProofPolicy.REQUIRED (F11) -> ReceiptStore/ReplayEngine (F7).

Ce module ne recrée AUCUNE logique de décision : il assemble strictement
build_paper_cycle_engine (execution/binder/paper_execution.py) avec les
composants réels disponibles. Aucune modification de build_paper_cycle_engine.

Composant métier honnêtement absent : ce repo n'a AUCUNE implémentation
réelle de StrategyPort/SizingPort (uniquement des doubles de test dans
tests/*). Le Reference Runtime observe donc le marché, fait voter les 17
agents, calcule un consensus réel (NativeRosterAggregation), et soumet ce
consensus au vrai Kernel — mais ne peut produire de TradeIntent dimensionné
tant qu'une vraie Strategy/Sizing n'est pas branchée (phase future).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from domain.calibration import CalibrationPack
from execution.binder.engine import CycleEngine, CycleOutcome
from execution.binder.paper_execution import (
    LiveModeRejected,
    build_paper_cycle_engine,
)
from execution.binder.proof_policy import ProofPolicy
from governance.bridge.kx108_client import KX108Unavailable, RealKX108Client
from market.adapters.alpaca.alpaca_config import AlpacaConfig, AlpacaConfigurationError
from native.agents.adapter import NativeRosterAnalysisAdapter
from native.agents.aggregation import NativeRosterAggregation
from native.agents.calibrated_agents import build_calibrated_trading_agents
from proof.receipts.receipt_store import ReceiptStore

_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
_RECEIPT_PATH = Path(__file__).resolve().parents[2] / "proof" / "receipts" / "data" / "cockpit_v2_reference_receipts.jsonl"
_ORDER_LEDGER_PATH = str(
    Path(__file__).resolve().parents[2] / "proof" / "receipts" / "data" / "cockpit_v2_reference_order_ledger.jsonl"
)


def _load_dotenv_into_process_env() -> None:
    """
    Charge .env (si présent) dans os.environ, sans dépendance python-dotenv
    (retirée en hygiène de release v0.2.1) — même mécanisme pur-Python que
    les tests d'intégration F13/F13.1. Ne journalise ni n'affiche jamais les
    valeurs. Idempotent : ne réécrit pas une variable déjà présente dans
    l'environnement du process.
    """
    if not _ENV_PATH.exists():
        return
    text = _ENV_PATH.read_bytes().decode("utf-8-sig")
    for line in text.splitlines():
        if "=" in line and line.strip():
            key, value = line.split("=", 1)
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = value.strip()


def alpaca_credentials_present() -> bool:
    """Présence (pas validité réseau) des identifiants Alpaca dans l'environnement du process."""
    _load_dotenv_into_process_env()
    return bool(os.environ.get("ALPACA_API_KEY")) and bool(os.environ.get("ALPACA_SECRET_KEY"))


def reference_runtime_status(kx108_observed: Optional[str] = None) -> Dict[str, Any]:
    """
    Statut du Reference Runtime AVANT tout cycle (Phase A2).

    `kx108_observed` : None tant qu'aucun round-trip réel n'a eu lieu dans
    cette session Streamlit ; sinon "CONNECTED" ou "UNAVAILABLE", REFLÉTANT
    un résultat réellement observé — jamais déduit de la simple construction
    de RealKX108Client (qui ne contacte rien à l'instanciation).
    """
    creds = alpaca_credentials_present()
    if kx108_observed == "CONNECTED":
        kx108_state = "REAL / CONNECTED"
    elif kx108_observed == "UNAVAILABLE":
        kx108_state = "REAL / UNAVAILABLE"
    elif creds:
        kx108_state = "REAL CLIENT CONFIGURED / NOT YET OBSERVED"
    else:
        kx108_state = "NOT CONFIGURED"
    return {
        "source": "NATIVE (17-agent roster, F13.1 calibration-aware where applicable)",
        "market": "Alpaca paper" if creds else "Alpaca paper (credentials absentes — .env non configuré)",
        "kx108": kx108_state,
        "mode": "PAPER",
        "proof": "REQUIRED",
        "binder": "ACTIVE (double barrière ExecutionPlanner, jamais contournée)",
        "execution": "PAPER ONLY (require_paper_mode, LIVE structurellement refusé)",
        "receipt": f"ReceiptStore -> {_RECEIPT_PATH.name}",
        "strategy_sizing": "ABSENT — aucune StrategyPort/SizingPort réelle dans ce repo (voir docstring module)",
    }


def build_reference_runtime_engine(symbol: str = "AAPL") -> CycleEngine:
    """
    Assemble le CycleEngine du Reference Runtime réel.

    Réutilise strictement build_paper_cycle_engine (F6) — aucune
    réimplémentation. RealKX108Client (F12) + ProofPolicy.REQUIRED (F11,
    verrouillé par construction avec RealKX108Client depuis F12.1) +
    NativeRosterAnalysisAdapter (F3) construit sur le roster calibré F13.1
    si un CalibrationPack réel est disponible pour ce symbole, sinon le
    roster natif standard (jamais de calibration fabriquée pour un symbole
    non couvert).
    """
    _load_dotenv_into_process_env()

    calibration_pack: Optional[CalibrationPack] = None
    agent_instances = build_calibrated_trading_agents(calibration_pack) if symbol == "AAPL" else None
    analysis = (
        NativeRosterAnalysisAdapter(agent_instances)
        if agent_instances is not None
        else NativeRosterAnalysisAdapter()
    )

    config = AlpacaConfig.from_env()
    return build_paper_cycle_engine(
        analysis=analysis,
        aggregation=NativeRosterAggregation(),
        kx108_client=RealKX108Client(),
        symbols=[symbol],
        order_ledger_path=_ORDER_LEDGER_PATH,
        alpaca_config=config,
        proof=ReceiptStore(_RECEIPT_PATH),
        proof_policy=ProofPolicy.REQUIRED,
    )


def run_reference_cycle(symbol: str = "AAPL") -> Dict[str, Any]:
    """
    Exécute un cycle réel unique. Retourne un dict {ok, outcome|error_kind,
    error_message, store}. N'appelle le Kernel QUE dans le cadre d'un cycle
    demandé explicitement par l'utilisateur — jamais pour fabriquer un
    verdict de santé (Phase A2).
    """
    try:
        engine = build_reference_runtime_engine(symbol)
    except (AlpacaConfigurationError, LiveModeRejected) as exc:
        return {"ok": False, "error_kind": type(exc).__name__, "error_message": str(exc)}

    try:
        outcome: CycleOutcome = engine.run_cycle()
    except KX108Unavailable as exc:
        return {"ok": False, "error_kind": "KX108Unavailable", "error_message": str(exc)}

    return {"ok": True, "outcome": outcome, "store": ReceiptStore(_RECEIPT_PATH)}
