"""
F12 — RealKX108Client : contract, parsing, fail-closed, boundary tests.

Utilise unittest.mock pour simuler le transport HTTP (rapide, deterministe,
independant du Kernel reel). La preuve du round-trip REEL est documentee
separement dans docs/F12_REAL_KERNEL_ROUND_TRIP.md (execution manuelle,
digests SHA-256 verifiables) car demarrer un process Node dans la suite
pytest serait fragile/non portable — ces tests couvrent le contrat
d'integration cote Trading, pas la disponibilite du Kernel lui-meme.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from governance.bridge.kx108_client import (
    KX108Unavailable,
    RealKX108Client,
)


def _fake_post(status_code=200, json_body=None, raise_status=False, json_error=False):
    def _post(url, json, timeout):  # noqa: A002 - matches requests.post signature
        resp = SimpleNamespace()
        resp.status_code = status_code

        def _raise_for_status():
            if raise_status:
                raise RuntimeError(f"HTTP {status_code}")

        resp.raise_for_status = _raise_for_status

        def _json():
            if json_error:
                raise ValueError("not json")
            return json_body

        resp.json = _json
        return resp

    return _post


IR_PAYLOAD = {
    "domain": "trading",
    "data": {"T_mean": 0.9, "H_score": 0.9, "A_score": 0.1, "S": 0.6},
    "meta": {"flow_type": "BUY", "ir_intent": "CREATE_PATCH", "risk_class": "", "gate_version": "v1"},
}


# ── Contract tests ──────────────────────────────────────────────────────


def test_sends_exact_ir_payload_shape():
    """Le client transmet le payload IR tel quel, sans le transformer."""
    captured = {}

    def _post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return SimpleNamespace(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: {"x108_gate": "HOLD"},
        )

    with patch("requests.post", side_effect=_post):
        client = RealKX108Client(base_url="http://127.0.0.1:3001/kernel/ragnarok")
        client.evaluate_trading(IR_PAYLOAD)

    assert captured["url"] == "http://127.0.0.1:3001/kernel/ragnarok"
    assert captured["json"] == IR_PAYLOAD


# ── Response parsing tests ──────────────────────────────────────────────


@pytest.mark.parametrize("raw_authority,expected", [("ACT", "ACT"), ("HOLD", "HOLD"), ("BLOCK", "BLOCK"), ("ALLOW", "ALLOW")])
def test_normalizes_x108_gate_field_to_verdict(raw_authority, expected):
    """Le Kernel reel repond avec 'x108_gate', jamais 'verdict' (F12 round-trip). Normalise correctement."""
    with patch("requests.post", side_effect=_fake_post(json_body={"x108_gate": raw_authority})):
        client = RealKX108Client()
        result = client.evaluate_trading(IR_PAYLOAD)

    assert result["verdict"] == expected


def test_existing_verdict_key_is_never_overwritten():
    with patch("requests.post", side_effect=_fake_post(json_body={"verdict": "ACT", "x108_gate": "BLOCK"})):
        client = RealKX108Client()
        result = client.evaluate_trading(IR_PAYLOAD)

    assert result["verdict"] == "ACT"  # le champ deja present prime, jamais ecrase


def test_unknown_x108_gate_value_is_not_invented_as_verdict():
    """Si x108_gate porte une valeur inconnue, le client n'invente rien."""
    with patch("requests.post", side_effect=_fake_post(json_body={"x108_gate": "MAYBE_LATER"})):
        client = RealKX108Client()
        result = client.evaluate_trading(IR_PAYLOAD)

    assert "verdict" not in result  # le Governance Bridge fail-close lui-meme


# ── Failure tests (fail-closed) ─────────────────────────────────────────


def test_kernel_unreachable_raises_kx108_unavailable():
    def _post(url, json, timeout):
        raise ConnectionError("refused")

    with patch("requests.post", side_effect=_post):
        client = RealKX108Client()
        with pytest.raises(KX108Unavailable):
            client.evaluate_trading(IR_PAYLOAD)


def test_timeout_raises_kx108_unavailable():
    def _post(url, json, timeout):
        raise TimeoutError("timed out")

    with patch("requests.post", side_effect=_post):
        client = RealKX108Client()
        with pytest.raises(KX108Unavailable):
            client.evaluate_trading(IR_PAYLOAD)


def test_malformed_json_raises_kx108_unavailable():
    with patch("requests.post", side_effect=_fake_post(json_error=True)):
        client = RealKX108Client()
        with pytest.raises(KX108Unavailable):
            client.evaluate_trading(IR_PAYLOAD)


def test_non_dict_response_raises_kx108_unavailable():
    with patch("requests.post", side_effect=_fake_post(json_body=["not", "a", "dict"])):
        client = RealKX108Client()
        with pytest.raises(KX108Unavailable):
            client.evaluate_trading(IR_PAYLOAD)


def test_http_error_status_raises_kx108_unavailable():
    with patch("requests.post", side_effect=_fake_post(status_code=500, raise_status=True)):
        client = RealKX108Client()
        with pytest.raises(KX108Unavailable):
            client.evaluate_trading(IR_PAYLOAD)


def test_missing_verdict_and_missing_x108_gate_is_fail_closed_downstream():
    """Reponse valide mais sans aucun champ d'autorite exploitable -> pas de verdict invente."""
    with patch("requests.post", side_effect=_fake_post(json_body={"some_other_field": 1})):
        client = RealKX108Client()
        result = client.evaluate_trading(IR_PAYLOAD)

    assert "verdict" not in result


# ── Boundary tests ───────────────────────────────────────────────────────


def test_real_kx108_client_module_has_no_decision_logic():
    """Aucune comparaison structurelle T/H/A/S, aucune formule, dans ce module."""
    import inspect

    import governance.bridge.kx108_client as mod

    source = inspect.getsource(mod)
    forbidden = ("T_mean", "H_score", "A_score", "structural_score", "theta_S")
    for token in forbidden:
        assert token not in source, f"RealKX108Client ne doit contenir aucune logique decisionnelle ({token})"


def test_real_kx108_client_never_imports_binder_or_broker():
    import inspect

    import governance.bridge.kx108_client as mod

    source = inspect.getsource(mod)
    assert "execution.binder" not in source
    assert "market.adapters.alpaca" not in source


def test_fixture_client_still_separate_from_real_client():
    """FixtureKX108Client (tests/test_support/) reste distinct de RealKX108Client, jamais confondus."""
    from tests.test_support.kx108_fixtures import FixtureKX108Client

    assert FixtureKX108Client is not RealKX108Client
