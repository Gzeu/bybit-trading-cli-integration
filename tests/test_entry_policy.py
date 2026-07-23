"""Tests for execution/entry_policy.py."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from skills.bybit_account_commander.src.execution.entry_policy import (
    decide_entry, compute_atr, compute_volume_sma
)


def _make_bars(n=50, trend=True):
    base = 100.0
    highs, lows, closes, volumes = [], [], [], []
    for i in range(n):
        c = base + (i * 0.5 if trend else 0)
        highs.append(c + 1.5)
        lows.append(c - 1.5)
        closes.append(c)
        volumes.append(1000.0 + i * 10)
    return highs, lows, closes, volumes


def test_atr_positive():
    h, l, c, v = _make_bars(50)
    atr = compute_atr(h, l, c)
    assert atr > 0


def test_volume_sma_positive():
    _, _, _, v = _make_bars(50)
    sma = compute_volume_sma(v, 20)
    assert sma > 0


def test_decide_entry_returns_dict():
    h, l, c, v = _make_bars(50)
    result = decide_entry(
        side="BUY",
        entry_price=c[-1],
        sar_price=c[-1] - 3.0,
        highs=h, lows=l, closes=c, volumes=v,
        rt_fee_rate=0.001,
        slip_estimate=0.0001,
    )
    assert "order_type" in result
    assert result["order_type"] in ("Market", "Limit")
    assert "time_in_force" in result


def test_postonly_when_prefer_postonly():
    h, l, c, v = _make_bars(50, trend=True)
    result = decide_entry(
        side="BUY",
        entry_price=c[-1],
        sar_price=c[-1] - 2.0,
        highs=h, lows=l, closes=c, volumes=v,
        rt_fee_rate=0.001,
        config={"fees": {"prefer_postonly": True}},
    )
    assert result["order_type"] == "Limit"
    assert result["time_in_force"] == "PostOnly"
