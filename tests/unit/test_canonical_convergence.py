"""
F8.7 — Canonical Convergence Closure.

Preuve qu'il n'existe plus qu'UN SEUL mecanisme de canonicalisation
(`domain.contracts.canonical.to_canonical_agent_signal`) emprunte a la fois
par le chemin Native (native/agents/adapter.py) et le chemin External
(external/normalization/normalizer.py). Aucune nouvelle fonctionnalite :
ces tests verifient une propriete architecturale, pas un comportement
metier nouveau.

Audit prealable (voir docs/MIGRATION_PROVENANCE.md, section F8.7) :
`to_canonical_agent_signal` ne contenait deja aucune hypothese specifique
au format ExternalSignal (CAS A) — seul l'appelant natif construisait
`AgentOutput(...)` directement au lieu de passer par cette fonction. Le
refactor a donc consiste a changer UNIQUEMENT `native/agents/adapter.py`,
sans toucher a `to_canonical_agent_signal`, `KX108GovernanceBridge`,
`execution/binder/`, `market/adapters/alpaca/`, ni la semantique du
receipt.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from domain.contracts.canonical import CanonicalAgentSignal, to_canonical_agent_signal
from domain.market import MarketSnapshot, Bar
from domain.types import AssetClass, DataQuality
from domain.portfolio import PortfolioState
from domain.provenance import SourceKind, SourceProvenance
from domain.proposal import AgentOutput
from domain.types import Mode, Provenance

from external.contracts.external_signal import ExternalSignal
from external.normalization.normalizer import normalize_external_signal
from native.agents.adapter import (
    NativeRosterAnalysisAdapter,
    agent_vote_to_agent_output,
    trading_state_from_snapshot,
)
from native.agents.contracts import AgentVote, Domain as NativeDomain, Severity


REPO_ROOT = Path(__file__).resolve().parents[2]


def _make_snapshot(symbol: str = "BTC/USD") -> MarketSnapshot:
    bars = [
        Bar(
            timestamp=float(i),
            open=100.0 + i,
            high=101.0 + i,
            low=99.0 + i,
            close=100.5 + i,
            volume=10.0,
        )
        for i in range(20)
    ]
    return MarketSnapshot(
        symbol=symbol,
        asset_class=AssetClass.CRYPTO,
        last_price=bars[-1].close,
        bars=tuple(bars),
        tradable=True,
        market_open=True,
        provenance=Provenance(source="test", fetched_at=0.0, quality=DataQuality.LIVE, mode=Mode.SIM),
    )


def _external_signal(**overrides) -> ExternalSignal:
    defaults = dict(
        source_id="brother_strategy_07",
        category="trading",
        signal="BUY",
        confidence=0.7,
        rationale="external test signal",
        unknowns=("liquidity_at_close",),
        contradictions=("momentum_vs_meanrev",),
        risk_flags=("concentration",),
        evidence_refs=("chart:1",),
        organization_id="brother_company",
        original_event_id="evt-1",
        observed_at=0.0,
        raw_payload={"note": "fixture"},
    )
    defaults.update(overrides)
    return ExternalSignal(**defaults)


# ---------------------------------------------------------------------------
# 1. Native utilise le meme primitif canonique qu'External (test structurel)
# ---------------------------------------------------------------------------


def test_native_adapter_calls_the_same_canonical_builder_as_external():
    native_src = inspect.getsource(agent_vote_to_agent_output)
    external_src = inspect.getsource(normalize_external_signal)
    assert "to_canonical_agent_signal(" in native_src
    assert "to_canonical_agent_signal(" in external_src
    # meme objet Python importe, pas une fonction homonyme redefinie ailleurs
    from native.agents import adapter as native_adapter_module
    from external.normalization import normalizer as external_normalizer_module

    assert native_adapter_module.to_canonical_agent_signal is to_canonical_agent_signal
    assert external_normalizer_module.to_canonical_agent_signal is to_canonical_agent_signal


# ---------------------------------------------------------------------------
# 2-6. Unknowns / contradictions / risk_flags / evidence_refs / provenance
#      survivent cote Native (bout en bout jusqu'a AgentOutput)
# ---------------------------------------------------------------------------


def _native_vote() -> AgentVote:
    return AgentVote(
        agent_id="MomentumAgent",
        vote="BUY",
        proposed_verdict="BUY",
        confidence=0.62,
        domain=NativeDomain.TRADING,
        layer=5,
        claim="momentum positive",
        contradictions=["mean_reversion_agent_disagrees"],
        unknowns=["next_earnings_date"],
        risk_flags=["thin_liquidity"],
        evidence_refs=["indicator:rsi=71"],
        severity_hint=Severity.S1,
    )


def test_native_unknowns_survive_to_agent_output():
    output = agent_vote_to_agent_output(_native_vote())
    assert output.unknowns == ("next_earnings_date",)


def test_native_contradictions_survive_to_agent_output():
    output = agent_vote_to_agent_output(_native_vote())
    assert output.contradictions == ("mean_reversion_agent_disagrees",)


def test_native_risk_flags_survive_to_agent_output():
    output = agent_vote_to_agent_output(_native_vote())
    assert output.risk_flags == ("thin_liquidity",)


def test_native_evidence_refs_survive_to_agent_output():
    output = agent_vote_to_agent_output(_native_vote())
    assert output.evidence_refs == ("indicator:rsi=71",)


def test_native_source_provenance_survives_to_agent_output():
    output = agent_vote_to_agent_output(_native_vote())
    assert output.source_provenance is not None
    assert output.source_provenance.source_system.value == "native"
    assert output.source_provenance.source_id == "MomentumAgent"


# ---------------------------------------------------------------------------
# 7. External reste fonctionnellement inchange
# ---------------------------------------------------------------------------


def test_external_normalization_unchanged_after_native_refactor():
    signal = _external_signal()
    result = normalize_external_signal(signal, adapter_id="brother_stack_v1")
    assert isinstance(result, AgentOutput)
    assert result.source_provenance.source_system.value == "external"
    assert result.source_provenance.source_id == "brother_strategy_07"
    assert result.source_provenance.adapter_id == "brother_stack_v1"
    assert result.unknowns == ("liquidity_at_close",)
    assert result.contradictions == ("momentum_vs_meanrev",)
    assert result.risk_flags == ("concentration",)
    assert result.evidence_refs == ("chart:1",)


# ---------------------------------------------------------------------------
# 8. Native et External produisent le meme TYPE canonique
# ---------------------------------------------------------------------------


def test_native_and_external_produce_the_same_canonical_type():
    native_output = agent_vote_to_agent_output(_native_vote())
    external_output = normalize_external_signal(_external_signal(), adapter_id="brother_stack_v1")
    assert type(native_output) is type(external_output) is CanonicalAgentSignal is AgentOutput


# ---------------------------------------------------------------------------
# 9. Aucune difference d'autorite entre les deux chemins
# ---------------------------------------------------------------------------


def test_provenance_alone_never_changes_decision_authority():
    """
    Deux AgentOutput identiques en tout sauf source_provenance ne doivent
    produire aucune divergence dans la facon dont le Governance Bridge (F5)
    les traite : la provenance est un champ transporte, jamais lu par la
    logique de decision. On le verifie ici en s'assurant qu'aucune branche
    de code de to_canonical_agent_signal ne conditionne le contenu du
    signal (confidence/signal/unknowns/...) sur la valeur de
    source_provenance.
    """
    native_like = to_canonical_agent_signal(
        agent_id="X",
        category="trading",
        signal="BUY",
        confidence=0.5,
        rationale="r",
        source_provenance=SourceProvenance.for_native_agent("X"),
    )
    external_like = to_canonical_agent_signal(
        agent_id="X",
        category="trading",
        signal="BUY",
        confidence=0.5,
        rationale="r",
        source_provenance=SourceProvenance.for_external_signal(
            source_id="X",
            source_kind=SourceKind.API,
            adapter_id="a",
            organization_id=None,
            original_event_id=None,
            observed_at=0.0,
        ),
    )
    assert native_like.signal == external_like.signal
    assert native_like.confidence == external_like.confidence
    assert native_like.category == external_like.category
    # seule la provenance differe
    assert native_like.source_provenance.source_system != external_like.source_provenance.source_system


# ---------------------------------------------------------------------------
# 10-11. Cycle Native / External complets toujours PASS
# ---------------------------------------------------------------------------
#
# Ces deux proprietes ne sont pas dupliquees ici : elles sont deja exercees
# de bout en bout par tests/integration/test_end_to_end_full_stack.py
# (chemin Native, scenario 1 notamment) et
# tests/integration/test_end_to_end_external_full_stack.py (chemin
# External, scenarios 1 et 2). Le refactor F8.7 ne modifie ni ces fichiers
# ni leur comportement attendu : `pytest tests/ -q` (suite complete, voir
# rapport F8.7) les fait tourner tels quels et ils restent verts apres ce
# changement. Un test structurel minimal ci-dessous confirme que
# NativeRosterAnalysisAdapter (utilise par ces scenarios) passe bien par la
# fonction canonique commune sur un cycle reel de bout en bout local.


def test_native_roster_adapter_full_analyse_uses_canonical_builder_end_to_end():
    adapter = NativeRosterAnalysisAdapter()
    snapshot = _make_snapshot()
    outputs = adapter.analyse("BTC/USD", snapshot, portfolio=None)
    assert len(outputs) == 17
    for output in outputs:
        assert isinstance(output, CanonicalAgentSignal)
        assert output.source_provenance is not None
        assert output.source_provenance.source_system.value == "native"


# ---------------------------------------------------------------------------
# 12. Suite globale zero regression -> verifie par le lancement complet de
#     `pytest tests/ -q` dans le rapport F8.7 (146 -> 158 passed attendus,
#     1 skipped, zero echec). Pas un test individuel: propriete de la suite.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Garde-fou architectural : un seul endroit construit un AgentOutput/
# CanonicalAgentSignal a partir de champs bruts (le builder lui-meme et ses
# tests exceptes). Empeche qu'un futur chemin Native (ou tout autre futur
# adapter) ne reconstruise silencieusement une deuxieme logique de
# canonicalisation en appelant `AgentOutput(...)` directement.
# ---------------------------------------------------------------------------


_ALLOWED_DIRECT_CONSTRUCTION_FILES = {
    # Le builder canonique lui-meme : c'est la SEULE implementation
    # autorisee a construire AgentOutput directement.
    "domain/proposal.py",
    "domain/contracts/canonical.py",
}


def _iter_source_files():
    for path in REPO_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if any(part in ("tests", ".git") for part in path.parts):
            continue
        yield path


def _constructs_agent_output_directly(path: Path) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name == "AgentOutput" and len(node.keywords) >= 4:
                # heuristique pragmatique : un appel a AgentOutput(...) avec
                # au moins 4 kwargs ressemble a une construction complete
                # (pas un simple update partiel type dataclasses.replace),
                # donc potentiellement une deuxieme logique de
                # canonicalisation. Les `dataclasses.replace(existing, ...)`
                # ne sont pas des appels a `AgentOutput(...)` et ne matchent
                # pas ce pattern.
                return True
    return False


def test_only_the_canonical_builder_constructs_agent_output_directly():
    offenders = []
    for path in _iter_source_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in _ALLOWED_DIRECT_CONSTRUCTION_FILES:
            continue
        if _constructs_agent_output_directly(path):
            offenders.append(rel)
    assert offenders == [], (
        "Construction directe de AgentOutput(...) detectee en dehors du "
        f"builder canonique : {offenders}. Tout producteur de signal "
        "d'agent (natif ou externe, present ou futur) doit passer par "
        "domain.contracts.canonical.to_canonical_agent_signal."
    )
