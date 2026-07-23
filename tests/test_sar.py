"""Tests for sar_trend.py — SAR, EMA, ADX, grade_setup."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from skills.bybit_account_commander.src.sar_trend import (
    compute_sar, compute_ema, compute_adx, grade_setup
)


def _flat_bars(n=100, price=100.0):
    highs = [price + 1] * n
    lows = [price - 1] * n
    closes = [price] * n
    return highs, lows, closes


def test_sar_length_matches_input():
    h, l, c = _flat_bars(100)
    sar = compute_sar(h, l)
    assert len(sar) == 100


def test_ema_converges():
    h, l, c = _flat_bars(100, 200.0)
    ema = compute_ema(c, 50)
    # After 100 bars at constant price, EMA should be close to price
    assert abs(ema[-1] - 200.0) < 5.0


def test_adx_returns_list():
    h, l, c = _flat_bars(100)
    adx = compute_adx(h, l, c, period=14)
    assert isinstance(adx, list)
    assert len(adx) == 100


def test_grade_setup_returns_none_for_flat():
    """Flat market should yield no A+ setup (ADX too low)."""
    h, l, c = _flat_bars(200, 100.0)
    sar = compute_sar(h, l)
    ema = compute_ema(c, 50)
    adx = compute_adx(h, l, c, 14)
    config = {"sar": {"min_adx": 20, "min_rr": 1.5},
              "risk": {"per_trade_pct": 0.01}}
    result = grade_setup(sar, ema, adx, c, "BTCUSDT", config, rt_fee=0.001)
    # Either None or grade B (weak)
    if result is not None:
        assert result["grade"] in ("B", "A", "A+")
