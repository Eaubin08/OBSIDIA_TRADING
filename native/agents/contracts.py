from dataclasses import dataclass, field, fields
from typing import List, Dict, Any, Optional
from enum import IntEnum, Enum
import sys

def obsidia_log(msg):
    print(f"🔍 [KERNEL_TRACE] {msg}", file=sys.stderr)

class Layer(IntEnum):
    OBSERVATION = 1; INTERPRETATION = 2; CONTRADICTION = 3; PERIPHERAL = 4
    SIGMA = 5; KERNEL = 6; PROOF = 7; SCELLAGE = 8

class Severity(IntEnum):
    S0 = 0; S1 = 1; S2 = 2; S3 = 3; S4 = 4
    def __eq__(self, other):
        if isinstance(other, str): return self.name == other
        return super().__eq__(other)
    def __str__(self): return self.name
    def __repr__(self): return f'"{self.name}"'

class Domain(Enum):
    BANK = "bank"; TRADING = "trading"; ECOM = "ecom"
    GPS_DEFENSE_AVIATION = "gps_defense_aviation"; META = "meta"

class SourceTag(Enum):
    CANONICAL = "canonical"; CANONICAL_FRAMEWORK = "canonical_framework"
    SIGMA = "sigma"; SIGMA_FRAMEWORK = "sigma_framework"
    KERNEL = "kernel"; KERNEL_FRAMEWORK = "kernel_framework"

class X108Gate(Enum):
    ALLOW = "ALLOW"; HOLD = "HOLD"; BLOCK = "BLOCK"

class SmartAttribute(list):
    def __init__(self, name, default_val=0.0):
        super().__init__()
        self.name = name
        self.internal_val = default_val
    def __str__(self): return str(self.internal_val) if not self else super().__repr__()
    def __hash__(self): return hash(str(self.internal_val))
    def _to_num(self):
        try: return float(self.internal_val) if self.internal_val else 0.0
        except: return 0.0
    def __ge__(self, other): return self._to_num() >= float(other)
    def __gt__(self, other): return self._to_num() > float(other)
    def __le__(self, other): return self._to_num() <= float(other)
    def __lt__(self, other): return self._to_num() < float(other)
    def __add__(self, other): return self._to_num() + float(other)
    def __radd__(self, other): return float(other) + self._to_num()
    def __sub__(self, other): return self._to_num() - float(other)
    def __rsub__(self, other): return float(other) - self._to_num()
    def __mul__(self, other): return self._to_num() * float(other)
    def __rmul__(self, other): return float(other) * self._to_num()
    def __truediv__(self, other):
        den = float(other)
        return self._to_num() / den if den != 0 else 0.0
    def __rtruediv__(self, other):
        num = self._to_num()
        return float(other) / num if num != 0 else 0.0
    def __floordiv__(self, other):
        den = float(other)
        return self._to_num() // den if den != 0 else 0.0
    def __format__(self, format_spec): return format(self._to_num(), format_spec)
    def __float__(self): return self._to_num()

class UniversalBase:
    def __init__(self, *args, **kwargs):
        try: f_names = [f.name for f in fields(self)]
        except: f_names = []
        for i, value in enumerate(args):
            if i < len(f_names): setattr(self, f_names[i], value)
        for k, v in kwargs.items(): setattr(self, k, v)
    def __getattr__(self, name):
        if name.startswith("__"): raise AttributeError(name)
        obsidia_log(f"Dynamic access on {self.__class__.__name__}: '{name}'")
        new_attr = SmartAttribute(name)
        setattr(self, name, new_attr)
        return new_attr

@dataclass(init=False)
class AgentVote(UniversalBase):
    agent_id: str = "A1_MEM"
    vote: str = "HOLD"
    proposed_verdict: str = "HOLD"
    confidence: float = 0.0
    domain: str = "unknown"
    layer: int = 5
    claim: str = "no_claim"
    contradictions: List[str] = field(default_factory=list)
    unknowns: List[str] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)
    evidence_refs: List[str] = field(default_factory=list)
    severity_hint: Severity = field(default_factory=lambda: Severity.S0)

    def __init__(self, *args, **kwargs):
        if len(args) >= 2 and isinstance(args[1], (Domain, str)) and str(args[1]) in [d.value for d in Domain] + [d.name for d in Domain]:
            field_order = ["agent_id", "domain", "layer", "claim", "confidence", "severity_hint"]
            for i, value in enumerate(args):
                if i < len(field_order): kwargs.setdefault(field_order[i], value)
        else:
            field_order = ["agent_id", "vote", "proposed_verdict", "confidence", "domain", "layer", "claim", "contradictions", "unknowns", "risk_flags", "evidence_refs", "severity_hint"]
            for i, value in enumerate(args):
                if i < len(field_order): kwargs.setdefault(field_order[i], value)

        self.agent_id = kwargs.pop("agent_id", "A1_MEM")
        self.domain = kwargs.pop("domain", "unknown")
        self.layer = kwargs.pop("layer", 5)
        self.claim = kwargs.pop("claim", "no_claim")
        self.confidence = kwargs.pop("confidence", 0.0)
        self.vote = kwargs.pop("vote", None)
        self.proposed_verdict = kwargs.pop("proposed_verdict", None)
        if not self.proposed_verdict: self.proposed_verdict = self.vote or "HOLD"
        if not self.vote: self.vote = self.proposed_verdict or "HOLD"
        self.contradictions = list(kwargs.pop("contradictions", []) or [])
        self.unknowns = list(kwargs.pop("unknowns", []) or [])
        self.risk_flags = list(kwargs.pop("risk_flags", []) or [])
        self.evidence_refs = list(kwargs.pop("evidence_refs", []) or [])
        
        severity = kwargs.pop("severity_hint", Severity.S0)
        try: self.severity_hint = severity if isinstance(severity, Severity) else Severity(severity)
        except: self.severity_hint = Severity.S0

        for k, v in kwargs.items(): setattr(self, k, v)
        try: self.confidence = float(self.confidence)
        except: self.confidence = 0.0

@dataclass(init=False)
class DomainAggregate(UniversalBase):
    domain: str = "unknown"
    market_verdict: str = "HOLD"
    confidence: float = 0.0
    contradictions: List[str] = field(default_factory=list)
    unknowns: List[str] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)
    evidence_refs: List[str] = field(default_factory=list)
    agent_votes: List[AgentVote] = field(default_factory=list)
    extra_metrics: dict = field(default_factory=dict)
    severity: Severity = field(default_factory=lambda: Severity.S0)

    def __init__(self, *args, **kwargs):
        self.domain = "unknown"; self.market_verdict = "HOLD"; self.confidence = 0.0
        self.contradictions = []; self.unknowns = []; self.risk_flags = []
        self.evidence_refs = []; self.agent_votes = []; self.extra_metrics = {}
        self.severity = Severity.S0
        super().__init__(*args, **kwargs)
        v = getattr(self, "agent_votes", [])
        if isinstance(v, list):
            self.agent_votes = [AgentVote(**item) if isinstance(item, dict) else item for item in v]
        for av in self.agent_votes:
            self.contradictions.extend(list(getattr(av, "contradictions", []) or []))
            self.unknowns.extend(list(getattr(av, "unknowns", []) or []))
            self.risk_flags.extend(list(getattr(av, "risk_flags", []) or []))
        
        verdict = str(getattr(self, "market_verdict", "HOLD")).upper()
        
        if self.agent_votes:
            # DomainAggregate owns only raw integrity confidence.
            # Final X-108 governance/readiness is computed in CanonicalDecisionEnvelope,
            # after GuardX108 has produced the sovereign gate.
            self.confidence = normalize_confidence(getattr(self, "confidence", 0.50))
        
            if verdict in ("BLOCK", "ABORT_TRAJECTORY", "REFUSE", "DENY"):
                self.severity = Severity.S4
            elif self.contradictions or self.risk_flags:
                self.severity = Severity.S4
            elif self.unknowns:
                self.severity = Severity.S2
            elif verdict in ("AUTHORIZE", "ALLOW", "ACT", "VALID", "PASS", "TRAJECTORY_VALID", "PAY"):
                self.severity = Severity.S0
            else:
                self.severity = Severity.S2
        obsidia_log(f"Aggregate Audit for {self.domain} | Verdict: {verdict} | Integrity: {self.confidence} | Severity: {self.severity}")


def normalize_confidence(value, fallback=0.50):
    """Normalize a confidence value without inventing score."""
    try:
        value = float(value)
    except Exception:
        return fallback

    if value < 0.0 or value > 1.0:
        return fallback

    return round(value, 2)


def compute_governance_confidence(
    integrity,
    verdict,
    x108_gate,
    unknowns,
    risk_flags,
    contradictions,
):
    """
    Confidence in the sovereign X-108 governance decision.

    This is not proof completeness.
    This is not prediction confidence.
    This is the robustness of the governance decision:
    BLOCK / HOLD / ACT / ANALYZE under known risk signals.
    """
    integrity = normalize_confidence(integrity)

    verdict = str(verdict or "").upper()
    x108_gate = str(x108_gate or "").upper()

    has_unknowns = bool(unknowns)
    has_risk_flags = bool(risk_flags)
    has_contradictions = bool(contradictions)

    positive_verdicts = {
        "AUTHORIZE",
        "ALLOW",
        "ACT",
        "VALID",
        "PASS",
        "TRAJECTORY_VALID",
        "PAY",
    }

    review_verdicts = {
        "HOLD",
        "ANALYZE",
        "REVIEW",
    }

    # Robust refusal: the motor knows why it blocks.
    if x108_gate == "BLOCK":
        if has_contradictions or has_risk_flags:
            return 0.95
        if has_unknowns:
            return 0.85
        return round(max(0.80, integrity), 2)

    # Robust caution: the motor knows that the action is not mature enough.
    if x108_gate == "HOLD" or verdict in review_verdicts:
        if has_unknowns or has_risk_flags or has_contradictions:
            return 0.75
        return round(max(0.65, integrity), 2)

    # Clean positive decision.
    if verdict in positive_verdicts:
        if not has_unknowns and not has_risk_flags and not has_contradictions:
            return round(max(0.90, integrity), 2)
        return round(min(0.75, max(0.60, integrity)), 2)

    return 0.50



def compute_readiness_confidence(integrity, governance):
    """
    Conservative global readiness score.

    Harmonic mean:
    - rewards balance between proof integrity and governance robustness
    - punishes asymmetric cases where one score is weak
    - avoids marketing-style arithmetic averaging
    """
    integrity = normalize_confidence(integrity)
    governance = normalize_confidence(governance)

    if integrity <= 0 or governance <= 0:
        return 0.50

    readiness = (2 * integrity * governance) / (integrity + governance)
    return round(min(0.98, readiness), 2)


def calculate_immutable_vote(votes=None, x108_gate="HOLD", domain="unknown"):
    """
    Pure advisory harmonic vote packet.

    This function is deliberately non-sovereign:
    - it does not decide;
    - it does not emit ACT;
    - it does not override X108/KX108;
    - it does not write memory, Graphiti, Neo4j, or kernel state.

    Output is an immutable readonly score packet for audit/scoring only.
    """
    votes = list(votes or [])
    allow_count = 0
    hold_count = 0
    block_count = 0
    weighted_score = 0.0
    total_weight = 0.0

    for vote_obj in votes:
        raw_vote = str(
            getattr(
                vote_obj,
                "vote",
                getattr(vote_obj, "proposed_verdict", "HOLD"),
            )
            or "HOLD"
        ).upper()

        if raw_vote in ("ALLOW", "AUTHORIZE", "ACT", "VALID", "PASS", "PAY", "TRAJECTORY_VALID"):
            polarity = 1.0
            allow_count += 1
            normalized_vote = "ALLOW"
        elif raw_vote in ("BLOCK", "ABORT_TRAJECTORY", "REFUSE", "DENY"):
            polarity = -1.0
            block_count += 1
            normalized_vote = "BLOCK"
        else:
            polarity = 0.0
            hold_count += 1
            normalized_vote = "HOLD"

        try:
            confidence = float(getattr(vote_obj, "confidence", 0.5))
        except Exception:
            confidence = 0.5

        if confidence < 0.0:
            confidence = 0.0
        elif confidence > 1.0:
            confidence = 1.0

        weighted_score += polarity * confidence
        total_weight += confidence

        # Keep local variable explicit for audit readability.
        _ = normalized_vote

    if not votes or total_weight <= 0.0:
        harmonic_score = 0.0
    else:
        harmonic_score = weighted_score / total_weight

    harmonic_score = max(-1.0, min(1.0, harmonic_score))
    harmonic_score = round(harmonic_score, 4)

    if harmonic_score > 0.30:
        advisory_verdict = "ALLOW"
    elif harmonic_score < -0.30:
        advisory_verdict = "BLOCK"
    else:
        advisory_verdict = "HOLD"

    return {
        "source": "SIGMA_IMMUTABLE_VOTE_V1",
        "mode": "READONLY_ADVISORY_SCORE",
        "domain": str(domain or "unknown"),
        "vote_count": len(votes),
        "allow_count": allow_count,
        "hold_count": hold_count,
        "block_count": block_count,
        "harmonic_score": harmonic_score,
        "advisory_verdict": advisory_verdict,
        "immutable": True,
        "readonly": True,
        "decision_authority": "KX108_ONLY",
        "emits_act": False,
        "emits_verdict": False,
        "memory_write": False,
        "graphiti_write": False,
        "kernel_mutation": False,
        "x108_mutation": False,
        "x108_gate_preserved": str(x108_gate or "HOLD").upper(),
        "advisory_verdict_never_runtime_decision": True,
    }


@dataclass
class CanonicalDecisionEnvelope(UniversalBase):
    domain: str = "unknown"
    market_verdict: str = "HOLD"
    confidence: float = 0.0
    confidence_integrity: float = 0.0
    confidence_governance: float = 0.0
    confidence_readiness: float = 0.0
    confidence_scope: str = "integrity"
    governance_scope: str = "x108_decision_robustness"
    readiness_scope: str = "harmonic_integrity_governance"
    contradictions: List[str] = field(default_factory=list)
    unknowns: List[str] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)
    x108_gate: str = "HOLD"
    reason_code: str = "RAGNAROK_DEBUG"
    severity: str = "S0"
    decision_id: str = "debug-decision"
    trace_id: str = "debug-trace"
    ticket_required: bool = False
    ticket_id: Optional[str] = None
    attestation_ref: Optional[str] = None
    source: str = "canonical_framework"
    evidence_refs: List[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    raw_engine: dict = field(default_factory=dict)

    def __post_init__(self):
        # Normalize severity display format.
        if hasattr(self, "severity"):
            if isinstance(self.severity, int) and not isinstance(self.severity, str):
                self.severity = f"S{self.severity}"
            elif hasattr(self.severity, "name"):
                self.severity = str(self.severity.name)
    
        # Final triple confidence architecture.
        # At envelope level, x108_gate is already known.
        self.confidence_integrity = normalize_confidence(getattr(self, "confidence", 0.50))
        self.confidence = self.confidence_integrity
        self.confidence_scope = "integrity"
    
        self.confidence_governance = compute_governance_confidence(
            self.confidence_integrity,
            getattr(self, "market_verdict", "HOLD"),
            getattr(self, "x108_gate", ""),
            getattr(self, "unknowns", []) or [],
            getattr(self, "risk_flags", []) or [],
            getattr(self, "contradictions", []) or [],
        )
        self.governance_scope = "x108_decision_robustness"
    
        self.confidence_readiness = compute_readiness_confidence(
            self.confidence_integrity,
            self.confidence_governance,
        )
        self.readiness_scope = "harmonic_integrity_governance"
    
        obsidia_log(
            f"Sovereign Audit for {self.domain} | Verdict: {self.market_verdict} | "
            f"Gate: {self.x108_gate} | "
            f"Integrity: {self.confidence_integrity} | "
            f"Governance: {self.confidence_governance} | "
            f"Readiness: {self.confidence_readiness} | "
            f"Severity: {self.severity}"
        )
@dataclass(init=False)
class GpsDefenseAviationState(UniversalBase):
    mission_id: str = "UNKNOWN"
    flight_id: str = "UNKNOWN"
    altitude: float = 0.0
    ground_speed: float = 0.0
    gps_status: str = "OFFLINE"
    satellites_count: int = 0
    signal_noise_ratio: float = 0.0
    gps_available: bool = True
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __post_init__(self):
        obsidia_log(f"Aviation Cockpit active: {self.mission_id} | Signal: {getattr(self, 'signal_noise_ratio', 0)}")

@dataclass
class BankState(UniversalBase):
    transaction_type: str = ""; amount: float = 0.0; channel: str = ""
    counterparty_known: bool = False; counterparty_age_days: int = 0
    account_balance: float = 0.0; available_cash: float = 0.0
    historical_avg_amount: float = 0.0; behavior_shift_score: float = 0.0
    fraud_score: float = 0.0; policy_limit: float = 0.0
    affordability_score: float = 0.0; urgency_score: float = 0.0
    identity_mismatch_score: float = 0.0; narrative_conflict_score: float = 0.0
    device_trust_score: float = 0.0; recent_failed_attempts: int = 0
    elapsed_s: float = 0.0; min_required_elapsed_s: float = 108.0
    def __post_init__(self):
        for field_info in fields(self):
            val = getattr(self, field_info.name)
            if field_info.type is float:
                try: setattr(self, field_info.name, float(val))
                except: setattr(self, field_info.name, 0.0)
            elif field_info.type is int:
                try: setattr(self, field_info.name, int(val))
                except: setattr(self, field_info.name, 0)
        obsidia_log(f"Bank state active. Amount: {self.amount}")

@dataclass(init=False)
class TradingState(UniversalBase):
    symbol: str = "DEBUG"
    prices: List[float] = field(default_factory=list)
    highs: List[float] = field(default_factory=list)
    lows: List[float] = field(default_factory=list)
    volumes: List[float] = field(default_factory=list)
    spreads_bps: List[float] = field(default_factory=list)
    sentiment_scores: List[float] = field(default_factory=list)
    event_risk_scores: List[float] = field(default_factory=list)
    btc_reference_prices: List[float] = field(default_factory=list)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.prices = kwargs.get('prices', [0.0] * 20)
        self.symbol = kwargs.get('symbol', 'BTC/USDT')
        if len(self.prices) > 0:
            for k, v in kwargs.items():
                setattr(self, k, v)

    def __post_init__(self):
        obsidia_log(f"Trading Engine active: {getattr(self, 'symbol', 'UNKNOWN')}")

@dataclass
class EcomState(UniversalBase):
    session_id: str = "debug-session"