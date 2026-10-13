# RECONCILE V1 REGISTER — OBSIDIA_TRADING

Branch: `reconcile/obsidia-trading-v1`
Date: 2026-10-13
Status: **ORGANIZATION_RECONCILED — RUNTIME_NOT_CERTIFIED**

Organizational closure tag: `org-reconciled/obsidia-trading-v1-20261013`, placed on commit `6965bff55fff27d510cd6f10116180127f17ed44`, the initial closure state. The tag was neither moved nor replaced. This version of the register is a later documentary correction (see §10). It certifies the Git organization only. **It is not a runtime freeze and not a new seal.** The sealed reference of this repository remains `obsidia-trading-v0.3.2-reference` on `master`, with `merkle_seal.json` unchanged.

No source branch was modified. Nothing was deleted. Nothing was merged into `master`. No PR was opened, closed, modified or merged. No other repository was touched. No broker was contacted: CI ran without any credentials.

## 1. Base

`master` @ `6dfee86778810829a2e9d89d3cc6caaaaa0996e9` — direct ancestor of all five work branches (none is behind), carrier of tag `obsidia-trading-v0.3.2-reference` and of the Merkle seal (93 sealed files, root hash `a51b8fb0211fd3a5f12cebe73b828524a0dad99f379e30285daea04e22cffca0`).

## 2. Integrated, in this order

| # | Source | Source SHA | Method | Resulting commit |
|---|---|---|---|---|
| 1 | `test/c41-v01-paper-proof-convergence-v0` | `4c2438d97191ec780369b230e597c711471243ca` | merge commit (GitHub merge API) | `b422cd5c7377f79245742c5e7ac6d7e889ea0c3e` |
| 2 | `fix/broker-ambiguity-truthfulness` | `57cca89dc2afb195d4b88583a9a0267be379d46a` | merge commit (GitHub merge API) | `14cbb9bcc1561888d4e89b0c49b6874dae51cfeb` |
| 3 | `feature/cockpit-v2-onboarding` | `2f9c42140f95222d41466c9baec34328d6966cc6` | merge commit (GitHub merge API) | `4c5eb14af2206e07550c45d664986b738098e18c` |
| 4 | `feature/f15-external-stack-readiness` | `f4e258b98e56d915277828eb4982db991d6921c4` | two-parent merge commit (Git Data API), one conflict resolved | `fa30bfa3b11b8cd4a7d3acc62d1668b15c7d3241` |

`feature/trading-product-core-v1` @ `383e21b90f3e920fde4af818dd1fe1f6d88003e4` (P1-A `998548e5b38513ea893e0a1457747f26ff90a423`, P1-B `69364ca72aa070a726419f5746b707462fc0febd`, P1-C `2def8c8cf07be3b959caa858765582f70aa1c4dd`, P1-D `383e21b9…`) is integrated through #2: it is an ancestor of `fix/broker-ambiguity-truthfulness`, whose 17 shared files are byte-identical to it.

Original commits (11 in total) are all reachable from this branch with their original SHA. Ancestry verified through the compare API (behind = 0) for `6dfee867`, `4c2438d9`, `383e21b9`, `57cca89d`, `2f9c4214`, `f4e258b9`.

Open draft PR #1 (`test/c41-…` → `master`) is left exactly as it was. `4c2438d9` is the SHA pinned by `obsidia-x108-proofs` C4.2; it has not moved.

## 3. Conflict resolved

| File | Branches | Nature | Resolution |
|---|---|---|---|
| `docs/MIGRATION_PROVENANCE.md` | `feature/f15-external-stack-readiness` and `feature/cockpit-v2-onboarding` | both append a section at the end of the file (GitHub merge API: HTTP 409) | both sections kept in full, chronological order: F15 (2026-09-23T03:44) then Cockpit V2 Phase A (2026-09-23T05:23) |

Byte-level check of the result (blob `d7d4d6183be9902ca28b1d348bb5ed9a6e9429dd`, 136 657 bytes): `master` content (129 731 bytes) + F15 section (5 178 bytes) + Cockpit V2 section (1 748 bytes). Removing the F15 section gives back the Cockpit V2 version exactly; the result starts with the F15 version exactly. Nothing removed, nothing rewritten.

No other conflict appeared. `native/agents/contracts.py` was merged automatically in step 3 (disjoint hunks: trace flag at the top of the file from Cockpit V2, `TradingState` fields from P1-A); both changes are present.

## 4. Tree integrity

- 231 files (198 on `master`), none deleted.
- 60 files differ from `master` = exactly the union of the files changed by the four integrated branches (0 missing, 0 extra).
- 58 of them are byte-identical to a source branch; the 2 others are the merged contents described in §3.
- Every other file is byte-identical to `master`.

## 5. Contracts

| Contract | Evidence |
|---|---|
| PAPER ONLY | `market/adapters/alpaca/alpaca_config.py` is byte-identical to `master` (default mode `paper`); `execution/binder/paper_execution.py` is the `fix/broker-ambiguity-truthfulness` version; PAPER pipeline tests pass. CI had no broker credentials |
| KX108_ONLY | `governance/bridge/kx108_client.py` is the `test/c41-…` version (canonical kernel authority); the F15 structural test forbidding `external/` to import the kernel client passes |
| Fail-closed | C4.1 PAPER proof set: 53 passed; sizing, proof-required and external validation tests pass |
| Receipts / replay | `tests/integration/test_replay.py` and `test_proof_required.py` are the `fix/broker-ambiguity-truthfulness` versions and pass |
| Seals and tags | `merkle_seal.json` byte-identical to `master`; the 8 reference tags unchanged |

## 6. Reconciliation-only commits

| SHA | Purpose |
|---|---|
| `36a60052c49b377f96857ceaa2d3282b560aceb3` | new file `.github/workflows/reconcile-v1-checks.yml` (push to `reconcile/**` only, Python 3.12, full history). The C4.1 workflow is unchanged |
| `6965bff55fff27d510cd6f10116180127f17ed44` | adds this register (commit carrying the organizational closure tag) |
| (this commit) | documentary correction of the register, posterior to the tag |

## 7. Tests

CI run `38356216289` on `36a60052c49b377f96857ceaa2d3282b560aceb3` (workflow `reconcile-v1-checks`): **failure**, reported as observed.

| Step | Result |
|---|---|
| C4.1 PAPER proof set (4 files, as in the source workflow) | success — 53 passed |
| Full test suite (`tests/`) | **1 failed, 449 passed, 22 skipped** |

The single failure:

```
tests/unit/test_freeze_manifest.py::test_merkle_seal_exists_and_root_hash_is_recomputable
AssertionError: le nombre de fichiers scelles a change depuis le calcul du seal
assert 93 == 104
```

Cause, known: `merkle_seal.json` describes `obsidia-trading-v0.3.2-reference` (93 sealed files). The integrated branches add and modify files inside the sealed scope without regenerating the seal, so the scope now holds 104 files. **This is the gap between this branch and the historical seal, not a defect of the merge.** The seal was deliberately not regenerated: doing so would seal a state that has not been validated.

The 22 skipped tests are the ones that need the real X-108 kernel (`node` / `server.kernel.sealed.cjs`, 11 tests), real Alpaca credentials (10 tests), or a legacy runtime outside scope (1 test); they skip by their own guards.

Four of the five work branches had never run in GitHub CI before.

## 8. Open items

| Item | Status |
|---|---|
| Merkle seal vs this branch | **OPEN_TECHNICAL_ITEM** — a new seal can only be produced after validation, in another mission |
| Real X-108 kernel round-trip | **PENDING** |
| Real Alpaca PAPER broker execution | **PENDING** |
| Real market data calibration | **PENDING** |
| Real external (third-party) trading stack | **PENDING** — F15 states it does not exist yet |

## 9. Guarantees

- `master` is still at `6dfee86778810829a2e9d89d3cc6caaaaa0996e9`.
- The 6 pre-existing branches and the 8 pre-existing tags are at the same SHA as before.
- PR #1 (open, draft, → `master`) is unchanged.
- No force-push, rebase or squash.

## 10. Corrections after closure

| Date | Correction |
|---|---|
| 2026-10-13 | §7: the number of tests skipped for lack of the real kernel is **11**, not 12 as written in the register at commit `6965bff5` (11 kernel + 10 Alpaca credentials + 1 legacy runtime = 22 skipped; the total was already correct). Documentation only: no code, test, workflow or seal was changed. The tag `org-reconciled/obsidia-trading-v1-20261013` still points to `6965bff55fff27d510cd6f10116180127f17ed44`; this commit comes after it on the branch |
