"""Tests for fees.py — net PnL, breakeven, edge gate."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from skills.bybit_account_commander.src.fees import compute_net_pnl, compute_breakeven, edge_gate


def test_net_pnl_long_win():
    net = compute_net_pnl(
        side="BUY", entry=100.0, exit_price=110.0,
        qty=1.0, fee_rate_entry=0.00055, fee_rate_exit=0.00055
    )
    assert net > 0, "Long winner should be positive"
    assert net < 10.0, "Net PnL should be less than gross (fees deducted)"


def test_net_pnl_short_win():
    net = compute_net_pnl(
        side="SELL", entry=110.0, exit_price=100.0,
        qty=1.0, fee_rate_entry=0.00055, fee_rate_exit=0.00055
    )
    assert net > 0


def test_net_pnl_long_loss():
    net = compute_net_pnl(
        side="BUY", entry=100.0, exit_price=95.0,
        qty=1.0, fee_rate_entry=0.00055, fee_rate_exit=0.00055
    )
    assert net < 0


def test_breakeven_above_entry_for_long():
    be = compute_breakeven(entry=100.0, qty=1.0, fee_rate=0.00055,
                           side="BUY")
    assert be > 100.0


def test_edge_gate_passes():
    ok, ratio = edge_gate(
        expected_gain=2.0, rt_fee=0.5,
        min_multiple=2.5
    )
    assert ok
    assert ratio >= 2.5


def test_edge_gate_fails():
    ok, ratio = edge_gate(
        expected_gain=0.5, rt_fee=0.5,
        min_multiple=2.5
    )
    assert not ok
    assert ratio < 2.5
