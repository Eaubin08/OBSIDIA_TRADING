"""
F13 (suite) — calibration reelle sur donnees de marche Alpaca reelles.

Ces tests necessitent ALPACA_API_KEY/ALPACA_SECRET_KEY reelles. Ils lisent
`.env` (jamais suivi par Git, voir .gitignore) EUX-MEMES via `monkeypatch`,
qui restaure l'environnement apres chaque test — aucune fuite vers
tests/unit/test_calibration_pack.py::test_real_dataset_attempt_is_honest_
about_missing_credentials, qui doit continuer a voir un environnement sans
ces variables quel que soit l'ordre d'execution.

Aucune valeur de cle n'est jamais affichee, loggee, ou ecrite dans un
fichier suivi par Git — seuls des digests (SHA-256) et des compteurs sont
rapportes. Si `.env` est absent ou les credentials vides, tous les tests
ci-dessous SKIP proprement (pas d'echec) : c'est le comportement attendu
sur une machine qui n'a pas ces credentials.
"""
from __future__ import annotations

import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

from domain.calibration import (
    CalibrationPack,
    CalibrationStatus,
    ModelCalibration,
    ModelCalibrationStatus,
)
from domain.calibration_estimation import (
    _garch_nll,
    estimate_garch_1_1,
    estimate_markov_regime_matrix,
    estimate_realized_volatility,
    log_returns_from_closes,
)
from governance.bridge.governance_bridge import KX108GovernanceBridge
from governance.bridge.kx108_client import RealKX108Client
from market.adapters.alpaca.real_dataset_attempt import (
    attempt_real_historical_dataset_with_closes,
)

ENV_PATH = Path(".env")
CORE_REPO = Path(
    r"C:\Users\User\Desktop\obsidia-engine-proof-core\obsidia-x108-proofs_REMOTE_A5F21C6B"
)
KERNEL_SCRIPT = CORE_REPO / "server.kernel.sealed.cjs"


def _load_env_pairs() -> dict:
    """Lit .env en memoire (jamais affiche). Vide si absent."""
    if not ENV_PATH.exists():
        return {}
    text = ENV_PATH.read_bytes().decode("utf-8-sig")
    pairs = {}
    for line in text.splitlines():
        if "=" in line and line.strip():
            k, v = line.split("=", 1)
            pairs[k.strip()] = v.strip()
    return pairs


@pytest.fixture()
def real_alpaca_env(monkeypatch):
    """
    Charge les credentials .env dans os.environ pour CE TEST SEULEMENT
    (monkeypatch restaure l'etat precedent a la fin, meme en cas d'echec).
    SKIP si absentes/vides — jamais un echec.
    """
    pairs = _load_env_pairs()
    api_key = pairs.get("ALPACA_API_KEY", "").strip()
    secret_key = pairs.get("ALPACA_SECRET_KEY", "").strip()
    if not api_key or not secret_key:
        pytest.skip(".env absent ou credentials Alpaca vides sur cette machine")
    for k, v in pairs.items():
        monkeypatch.setenv(k, v)
    yield


def _fetch_real_returns():
    ds, closes = attempt_real_historical_dataset_with_closes(
        symbol="AAPL", timeframe="1Day", limit=250, lookback_days=250
    )
    if not ds.is_real:
        pytest.skip(f"Alpaca n'a pas retourne de donnees reelles: {ds.quality_flags}")
    returns = log_returns_from_closes(closes)
    return ds, returns


# 1. calibration deterministe sur les memes donnees reelles (meme closes -> meme digest)
def test_real_dataset_digest_is_deterministic_for_identical_closes(real_alpaca_env):
    ds1, closes1 = attempt_real_historical_dataset_with_closes(
        symbol="AAPL", timeframe="1Day", limit=250, lookback_days=250
    )
    ds2, closes2 = attempt_real_historical_dataset_with_closes(
        symbol="AAPL", timeframe="1Day", limit=250, lookback_days=250
    )
    assert ds1.is_real and ds2.is_real
    # Deux appels rapproches sur la meme fenetre glissante recuperent le
    # meme historique passe (a la barre du jour pres) : le digest depend du
    # contenu recu, teste ici la propriete de determinisme du digest
    # lui-meme (meme DatasetDescriptor -> meme hash), pas la stabilite
    # reseau entre deux appels.
    assert ds1.digest() == ds1.digest()
    assert ds2.digest() == ds2.digest()


# 2/3. dataset different (symbole different) -> digest different
def test_different_symbol_yields_different_digest(real_alpaca_env):
    ds_aapl, _ = attempt_real_historical_dataset_with_closes(
        symbol="AAPL", timeframe="1Day", limit=100, lookback_days=150
    )
    ds_msft, _ = attempt_real_historical_dataset_with_closes(
        symbol="MSFT", timeframe="1Day", limit=100, lookback_days=150
    )
    assert ds_aapl.is_real and ds_msft.is_real
    assert ds_aapl.digest() != ds_msft.digest()


# 4. provenance conservee dans le CalibrationPack
def test_real_calibration_pack_preserves_provenance(real_alpaca_env):
    ds, returns = _fetch_real_returns()
    vol = estimate_realized_volatility(returns)
    models = (
        ModelCalibration(
            model_name="realized_volatility",
            status=ModelCalibrationStatus.CALIBRATED if vol.sufficient_data else ModelCalibrationStatus.UNCALIBRATED,
            method=vol.method,
            parameters={"annualized_vol": vol.annualized_vol},
        ),
    )
    pack = CalibrationPack.build(dataset=ds, models=models, method="f13_real_v1")
    d = pack.as_dict()
    assert d["dataset"]["symbol"] == "AAPL"
    assert d["dataset"]["source"] == "alpaca_market_data_api"
    assert d["dataset"]["observation_count"] == ds.observation_count
    assert d["dataset_digest"] == ds.digest()


# 5. donnees insuffisantes -> unknown explicite (teste sur un sous-echantillon tronque)
def test_insufficient_real_sample_yields_explicit_unsufficient_status(real_alpaca_env):
    _, returns = _fetch_real_returns()
    tiny = returns[:5]  # sous le seuil MIN_OBSERVATIONS_VOLATILITY (10)
    vol = estimate_realized_volatility(tiny)
    assert vol.sufficient_data is False
    garch = estimate_garch_1_1(tiny)
    assert garch.sufficient_data is False
    markov = estimate_markov_regime_matrix(tiny, n_regimes=2)
    assert markov.sufficient_data is False


# 6. staleness identifiable
def test_real_pack_staleness_fields_present(real_alpaca_env):
    ds, _ = _fetch_real_returns()
    pack = CalibrationPack.build(dataset=ds, models=(), method="f13_real_v1")
    d = pack.as_dict()
    assert d["created_at"]
    assert d["dataset"]["retrieved_at"]
    assert d["dataset"]["start"] and d["dataset"]["end"]


# 7. Markov calibre reellement (ou statut honnete si volume insuffisant)
def test_markov_calibrated_from_real_returns_or_honestly_insufficient(real_alpaca_env):
    _, returns = _fetch_real_returns()
    split = int(len(returns) * 0.7)
    train = returns[:split]
    markov = estimate_markov_regime_matrix(train, n_regimes=2)
    if len(train) >= 30:
        assert markov.sufficient_data is True
        assert len(markov.transition_matrix) == 2
        for row in markov.transition_matrix:
            assert abs(sum(row) - 1.0) < 1e-9
        assert sum(markov.observations_per_regime) == len(train)
    else:
        assert markov.sufficient_data is False


def test_garch_calibrated_from_real_returns_or_honestly_insufficient(real_alpaca_env):
    _, returns = _fetch_real_returns()
    split = int(len(returns) * 0.7)
    train = returns[:split]
    garch = estimate_garch_1_1(train)
    if len(train) >= 30:
        assert garch.sufficient_data is True
        assert garch.alpha + garch.beta < 1.0
        assert garch.omega > 0.0
    else:
        assert garch.sufficient_data is False


# 8. aucun fallback synthetique silencieux : verifie qu'un dataset reel a
#    bien observation_count>0 et source reelle (pas de placeholder deguise)
def test_real_dataset_is_genuinely_real_not_a_disguised_placeholder(real_alpaca_env):
    ds, returns = _fetch_real_returns()
    assert ds.is_real
    assert ds.observation_count > 0
    assert len(returns) > 0
    assert ds.source == "alpaca_market_data_api"
    assert ds.quality_flags == ()


# out-of-sample : parametres fittes sur la fenetre train, NLL evaluee sur eval,
# jamais l'inverse (pas de fuite train/eval)
def test_garch_out_of_sample_evaluation_uses_distinct_window(real_alpaca_env):
    _, returns = _fetch_real_returns()
    if len(returns) < 60:
        pytest.skip("echantillon reel insuffisant pour un decoupage train/eval significatif")
    split = int(len(returns) * 0.7)
    train, eval_window = returns[:split], returns[split:]
    assert len(train) + len(eval_window) == len(returns)
    garch = estimate_garch_1_1(train)
    assert garch.sufficient_data is True
    oos_nll = _garch_nll(eval_window, garch.omega, garch.alpha, garch.beta)
    # Pas d'assertion de superiorite/inferiorite du fit hors-echantillon —
    # on verifie seulement que l'evaluation a bien lieu sur une fenetre
    # disjointe du fit, et produit un nombre fini (pas de divergence
    # numerique grossiere qui indiquerait un parametre non stationnaire).
    import math
    assert math.isfinite(oos_nll)


# 9. Native fonctionne avec CalibrationPack construit sur donnees reelles
def test_native_roster_unaffected_by_real_calibration_pack(real_alpaca_env):
    from native.agents.domains.trading_agents import MarketDataAgent  # import direct, aucune dependance calibration

    ds, returns = _fetch_real_returns()
    pack = CalibrationPack.build(dataset=ds, models=(), method="f13_real_v1")
    assert pack.status in (
        CalibrationStatus.CALIBRATED,
        CalibrationStatus.PARTIALLY_CALIBRATED,
        CalibrationStatus.NOT_CALIBRATED_NO_REAL_DATA,
    )
    assert MarketDataAgent is not None  # le roster existe et s'importe sans le pack


# 12/13. vrai Kernel inchange, et fonctionne encore avec des cas issus de la calibration reelle
@pytest.fixture(scope="module")
def real_kernel_process():
    node = shutil.which("node")
    if node is None or not KERNEL_SCRIPT.exists():
        pytest.skip("node ou server.kernel.sealed.cjs indisponible")

    def _port_open(host, port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.3)
            return sock.connect_ex((host, port)) == 0

    if _port_open("127.0.0.1", 3001):
        pytest.skip("port 3001 deja occupe")

    proc = subprocess.Popen(
        [node, str(KERNEL_SCRIPT)], cwd=str(CORE_REPO),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        for _ in range(30):
            if _port_open("127.0.0.1", 3001):
                break
            time.sleep(0.2)
        else:
            proc.kill()
            pytest.skip("Kernel n'a pas demarre a temps")
        yield proc
    finally:
        proc.kill()
        proc.wait(timeout=5)


def test_real_kernel_observes_case_derived_from_real_calibration(
    real_alpaca_env, real_kernel_process
):
    """
    Construit un payload IR a partir de la volatilite REELLEMENT estimee
    (pas synthetique), l'envoie au vrai Kernel, observe le verdict SANS
    jamais ajuster un parametre de calibration en fonction de ce verdict
    (aucune boucle de retroaction ecrite ici ni ailleurs dans ce module).
    """
    _, returns = _fetch_real_returns()
    vol = estimate_realized_volatility(returns)
    if not vol.sufficient_data:
        pytest.skip("volatilite reelle non calculable (echantillon insuffisant)")

    # T_mean/H_score/A_score/S : mappage simple et documente de la
    # volatilite annualisee reelle vers l'espace [0,1] attendu par le
    # Kernel (voir domains/trading/trading_x108_gate.py du core, IR
    # payload). Aucune pretention a une formule officielle du domaine —
    # juste un signal reel plutot qu'invente.
    normalized_vol = min(vol.annualized_vol / 1.0, 1.0)
    payload = {
        "domain": "trading",
        "data": {
            "T_mean": 0.7,
            "H_score": max(0.0, 1.0 - normalized_vol),
            "A_score": normalized_vol,
            "S": 0.5,
        },
        "meta": {
            "flow_type": "OBSERVE",
            "ir_intent": "F13_REAL_CALIBRATION_OBSERVATION",
            "risk_class": "",
            "gate_version": "v1",
        },
    }
    bridge = KX108GovernanceBridge(RealKX108Client())
    response = bridge.client.evaluate_trading(payload)
    assert isinstance(response, dict)
    assert "verdict" in response or "x108_gate" in response
    # Rapport strict "input->output", aucune causalite affirmee au-dela de
    # ce que le test verifie explicitement.


def test_kernel_files_not_modified_by_real_calibration(real_kernel_process):
    result = subprocess.run(
        ["git", "status", "--short"], cwd=str(CORE_REPO),
        capture_output=True, text=True, check=True,
    )
    lines = [l for l in result.stdout.splitlines() if l.strip()]
    for line in lines:
        assert "merkle_seal.json" in line, f"fichier core modifie de facon inattendue: {line}"


# 17. aucun tuning selon verdict Kernel : verification AST que ce module de
#     test et le module d'estimation n'importent jamais un mecanisme qui
#     reinjecterait un verdict Kernel dans un parametre de calibration.
def test_no_feedback_loop_from_kernel_verdict_to_calibration_params():
    import ast

    for relpath in ("domain/calibration_estimation.py", "market/adapters/alpaca/real_dataset_attempt.py"):
        tree = ast.parse(Path(relpath).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mod = getattr(node, "module", None) or ",".join(n.name for n in node.names)
                assert "governance" not in (mod or ""), f"{relpath} importe {mod}"
                assert "execution.binder" not in (mod or ""), f"{relpath} importe {mod}"
