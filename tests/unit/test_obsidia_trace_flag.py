"""
Cockpit V2 Phase A6/A9 — obsidia_log() derriere OBSIDIA_TRACE, opt-in.

Aucun changement comportemental agents/etat : seul le canal stderr change.
"""
from __future__ import annotations

from native.agents.contracts import obsidia_log


def test_trace_off_by_default_produces_no_output(monkeypatch, capsys):
    monkeypatch.delenv("OBSIDIA_TRACE", raising=False)
    obsidia_log("test message")
    captured = capsys.readouterr()
    assert "KERNEL_TRACE" not in captured.err
    assert "KERNEL_TRACE" not in captured.out


def test_trace_on_with_env_flag_produces_output(monkeypatch, capsys):
    monkeypatch.setenv("OBSIDIA_TRACE", "1")
    obsidia_log("test message")
    captured = capsys.readouterr()
    assert "KERNEL_TRACE" in captured.err
    assert "test message" in captured.err


def test_trace_any_other_value_stays_off(monkeypatch, capsys):
    monkeypatch.setenv("OBSIDIA_TRACE", "0")
    obsidia_log("test message")
    captured = capsys.readouterr()
    assert "KERNEL_TRACE" not in captured.err
