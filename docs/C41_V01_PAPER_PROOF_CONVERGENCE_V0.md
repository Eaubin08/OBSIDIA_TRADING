# C4.1 — Trading V0.1 PAPER + Proof Boundary

Date: 2026-10-08  
Scope: `OBSIDIA_TRADING` runtime / canonical bridge, not private core edits.

## Why this patch

Trading F12 has a **historically demonstrated real** HTTP round-trip through
the sealed KX108 kernel, but `RealKX108Client` is not configured by default
and most portable test flows use `FixtureKX108Client`. The existing tests
demonstrated a contract ambiguity: if `verdict=ACT` coexisted with
`x108_gate=BLOCK`, the Trading HTTP client trusted the legacy `verdict`.
This could represent the opposite of the canonical response.

C4.1 makes `x108_gate` canonical. A conflicting/malformed field removes
the legacy `verdict`, allowing the unchanged Governance Bridge to fail closed
as `HOLD`. Only exact consistent canonical/legacy authority is transported.
This is normalization, **not** a new decision engine.

## New regression

The new `tests/integration/test_c41_v01_paper_proof_convergence_v0.py`
tests the *existing* Trading CycleEngine/Bridge/Binder/FakeBroker under
PAPER with `ProofPolicy.REQUIRED`. Cases include:

- Native roster and External adapter with KX client unavailable -> no order;
- malformed or contradictory canonical/legacy response -> no order;
- real-client-path mocked HTTP `HOLD`/`BLOCK` -> no order;
- RealKernel cannot be constructed with BEST_EFFORT;
- fixture KX ACT and proof-store unavailable -> no broker call;
- LIVE mode rejected by the existing paper assembly.

All network/broker paths are fakes. Tests do not contact Alpaca or X108.
The true historical F12 evidence remains distinct, and there is no claim of
a V0.1 enterprise-live Trading integration.

The Trading repo's existing source/adapter/contracts are reused; no second
Domain Pack or paper executor is introduced.

## Production blockers

Tenant-scoped delegation/identity (C2), concrete V0.1-to-Trading signal
contract integration, real kernel endpoint attestation & receipt verification,
broker-grade replay/idempotency and independent PAPER partner test.
No LIVE trading. No changes to `main` or `KX108`.
