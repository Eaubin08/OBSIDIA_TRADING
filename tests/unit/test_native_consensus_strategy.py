"""
P1-B — Native Reference Strategy.

Preuve que `NativeReferenceStrategy` transcrit honnetement le Consensus
Native sans jamais decider ACT/HOLD/BLOCK, dimensionner une position, ou
inventer stop_loss/take_profit/horizon_s/expected_risk. Statut derive
uniquement d'evidence semantique explicite (opposing_evidence/degraded_inputs
et statut d'Opportunity), jamais d'un seuil numerique arbitraire sur
agreement_ratio/confidence/poids.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from domain.market import Bar, MarketSnapshot
from domain.portfolio import AccountState, PortfolioState
from domain.proposal import Consensus, Opportunity, StrategyCandidate
from domain.types import ActionKind, AssetClass, DataQuality, Mode, Provenance

from native.strategy.native_consensus_strategy import NativeReferenceStrategy


def _bars(n: int = 5, base: float = 100.0):
    out = []
    price = base
    for i in range(n):
        out.append(Bar(timestamp=float(i), open=price, high=price, low=price, close=price, volume=1_000.0))
    return tuple(out)


def _provenance() -> Provenance:
    return Provenance(source="test", fetched_at=0.0, quality=DataQuality.LIVE, mode=Mode.PAPER)


def _snapshot(symbol: str = "AAPL") -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol, asset_class=AssetClass.EQUITY, last_price=100.0,
        provenance=_provenance(), bars=_bars(),
    )


def _portfolio() -> PortfolioState:
    account = AccountState(
        equity=100_000.0, cash=100_000.0, buying_power=100_000.0,
        provenance=_provenance(), trading_blocked=False,
    )
    return PortfolioState(account=account)


def _consensus(side: str, confidence: float = 0.7, **kwargs) -> Consensus:
    return Consensus(side=side, confidence=confidence, **kwargs)


def _opportunity(symbol: str = "AAPL", status: str = "VALID") -> Opportunity:
    return Opportunity(symbol=symbol, score=0.5, kind="test", rationale="test", status=status)


STRATEGY = NativeReferenceStrategy()


# --- 1. HOLD -> pas de strategie -------------------------------------------

def test_hold_yields_empty_sequence():
    candidates = STRATEGY.build("AAPL", _snapshot(), _consensus("HOLD"), _portfolio())
    assert candidates == ()


# --- 2. BUY -> exactement une candidate BUY --------------------------------

def test_buy_yields_exactly_one_buy_candidate():
    candidates = STRATEGY.build("AAPL", _snapshot(), _consensus("BUY"), _portfolio())
    assert len(candidates) == 1
    assert candidates[0].action == ActionKind.BUY


# --- 3. SELL -> exactement une candidate SELL ------------------------------

def test_sell_yields_exactly_one_sell_candidate():
    candidates = STRATEGY.build("AAPL", _snapshot(), _consensus("SELL"), _portfolio())
    assert len(candidates) == 1
    assert candidates[0].action == ActionKind.SELL


# --- 4. side inconnu -> pas de candidate, jamais de direction devinee -----

@pytest.mark.parametrize("side", ["WAIT", "UNKNOWN", "", "buy", "Buy"])
def test_unknown_or_unexpected_side_yields_no_candidate(side):
    candidates = STRATEGY.build("AAPL", _snapshot(), _consensus(side), _portfolio())
    assert candidates == ()


# --- 5. confidence preservee exactement, sans transformation ---------------

def test_confidence_preserved_exactly():
    candidates = STRATEGY.build("AAPL", _snapshot(), _consensus("BUY", confidence=0.6789), _portfolio())
    assert candidates[0].confidence == 0.6789


# --- 6. opposing_evidence -> CONFLICTED ------------------------------------

def test_opposing_evidence_yields_conflicted_status():
    consensus = _consensus("BUY", opposing_evidence=("agent-x-dissent",))
    candidates = STRATEGY.build("AAPL", _snapshot(), consensus, _portfolio())
    assert candidates[0].status == "CONFLICTED"
    assert candidates[0].opposing_evidence == ("agent-x-dissent",)


# --- 7. Opportunity CONFLICTED -> CONFLICTED -------------------------------

def test_opportunity_conflicted_yields_conflicted_status():
    opp = _opportunity(status="CONFLICTED")
    candidates = STRATEGY.build("AAPL", _snapshot(), _consensus("BUY"), _portfolio(), opportunities=(opp,))
    assert candidates[0].status == "CONFLICTED"


# --- 8. degraded_inputs -> WEAK --------------------------------------------

def test_degraded_inputs_yields_weak_status():
    consensus = _consensus("BUY", degraded_inputs=("spread_missing",))
    candidates = STRATEGY.build("AAPL", _snapshot(), consensus, _portfolio())
    assert candidates[0].status == "WEAK"


# --- 9. Opportunity WEAK -> WEAK -------------------------------------------

def test_opportunity_weak_yields_weak_status():
    opp = _opportunity(status="WEAK")
    candidates = STRATEGY.build("AAPL", _snapshot(), _consensus("BUY"), _portfolio(), opportunities=(opp,))
    assert candidates[0].status == "WEAK"


# --- 10. Opportunity DEGRADED -> WEAK --------------------------------------

def test_opportunity_degraded_yields_weak_status():
    opp = _opportunity(status="DEGRADED")
    candidates = STRATEGY.build("AAPL", _snapshot(), _consensus("BUY"), _portfolio(), opportunities=(opp,))
    assert candidates[0].status == "WEAK"


# --- 11. Consensus propre, aucune Opportunity -> VALID ---------------------

def test_clean_consensus_yields_valid_status():
    candidates = STRATEGY.build("AAPL", _snapshot(), _consensus("BUY"), _portfolio())
    assert candidates[0].status == "VALID"


# --- 12. precedence CONFLICTED > WEAK --------------------------------------

def test_conflicted_takes_precedence_over_weak():
    consensus = _consensus(
        "BUY",
        opposing_evidence=("agent-x-dissent",),
        degraded_inputs=("spread_missing",),
    )
    candidates = STRATEGY.build("AAPL", _snapshot(), consensus, _portfolio())
    assert candidates[0].status == "CONFLICTED"


# --- 13-16. rien d'invente sur les champs de sortie/risque -----------------

def test_no_stop_loss_invented():
    candidates = STRATEGY.build("AAPL", _snapshot(), _consensus("BUY"), _portfolio())
    assert candidates[0].stop_loss is None


def test_no_take_profit_invented():
    candidates = STRATEGY.build("AAPL", _snapshot(), _consensus("BUY"), _portfolio())
    assert candidates[0].take_profit is None


def test_no_horizon_invented():
    candidates = STRATEGY.build("AAPL", _snapshot(), _consensus("BUY"), _portfolio())
    assert candidates[0].horizon_s is None


def test_no_expected_risk_invented():
    candidates = STRATEGY.build("AAPL", _snapshot(), _consensus("BUY"), _portfolio())
    assert candidates[0].expected_risk is None


# --- 17. aucune logique de sizing (StrategyCandidate ne porte pas de qty) --

def test_strategy_candidate_carries_no_sizing_quantity():
    candidates = STRATEGY.build("AAPL", _snapshot(), _consensus("BUY"), _portfolio())
    assert not hasattr(candidates[0], "quantity")
    assert not hasattr(candidates[0], "requested_quantity")


# --- 18. aucune production d'Authority -------------------------------------

def test_strategy_produces_no_authority_type():
    candidates = STRATEGY.build("AAPL", _snapshot(), _consensus("BUY"), _portfolio())
    assert all(isinstance(c, StrategyCandidate) for c in candidates)
    for c in candidates:
        assert not hasattr(c, "authority")
        assert not hasattr(c, "verdict")


# --- 19. aucun import governance/bridge (test structurel AST) --------------

def test_no_governance_import_in_strategy_module():
    src = Path("native/strategy/native_consensus_strategy.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = getattr(node, "module", None) or ",".join(n.name for n in node.names)
            assert "governance" not in (mod or ""), f"import interdit trouve: {mod}"
            assert "execution.binder" not in (mod or ""), f"import interdit trouve: {mod}"
            assert "market.adapters" not in (mod or ""), f"import interdit trouve: {mod}"


# --- 20. determinisme : meme input -> meme candidate ------------------------

def test_same_input_yields_same_candidate_deterministically():
    consensus = _consensus("BUY", confidence=0.5432, opposing_evidence=("x",))
    snapshot = _snapshot()
    portfolio = _portfolio()
    c1 = STRATEGY.build("AAPL", snapshot, consensus, portfolio)
    c2 = STRATEGY.build("AAPL", snapshot, consensus, portfolio)
    assert c1 == c2


# --- extra: opportunity_id preserve pour le symbole pertinent, pas les autres

def test_opportunity_id_preserved_only_for_relevant_symbol():
    opp_aapl = _opportunity(symbol="AAPL", status="VALID")
    opp_msft = Opportunity(symbol="MSFT", score=0.9, kind="test", rationale="other symbol", status="VALID")
    candidates = STRATEGY.build(
        "AAPL", _snapshot(), _consensus("BUY"), _portfolio(), opportunities=(opp_msft, opp_aapl)
    )
    assert candidates[0].opportunity_id == opp_aapl.opportunity_id


# --- extra: aucune Opportunity requise pour produire une candidate ---------

def test_no_opportunity_required_to_produce_candidate():
    candidates = STRATEGY.build("AAPL", _snapshot(), _consensus("BUY"), _portfolio(), opportunities=())
    assert len(candidates) == 1
    assert candidates[0].opportunity_id == ""


# --- extra: portfolio absent (None) n'empeche pas la transcription --------

def test_missing_portfolio_does_not_block_transcription():
    candidates = STRATEGY.build("AAPL", _snapshot(), _consensus("BUY"), None)
    assert len(candidates) == 1


# --- extra: entry_price/invalidation/constraints/required_conditions non fabriques --

def test_no_fabricated_entry_price_or_constraints():
    candidates = STRATEGY.build("AAPL", _snapshot(), _consensus("BUY"), _portfolio())
    c = candidates[0]
    assert c.entry_price is None
    assert c.constraints == ()
    assert c.required_conditions == ()


# --- extra: provenance stable et explicite ---------------------------------

def test_provenance_is_stable_and_explicit():
    candidates = STRATEGY.build("AAPL", _snapshot(), _consensus("BUY"), _portfolio())
    assert candidates[0].provenance == "native_reference_strategy.v1"
