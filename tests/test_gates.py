"""Tests for gates.py — pre-trade checklist."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from skills.bybit_account_commander.src.gates import check_all_gates


def _snapshot(equity=100.0, imr=0.0, daily_pnl=0.0):
    return {
        "total_equity": equity,
        "initial_margin": imr,
        "daily_pnl": daily_pnl,
    }


def _action(risk_usdt=0.75, leverage=10, rr=2.0):
    return {
        "type": "EXECUTE",
        "action": "open_perp_sar",
        "symbol": "BTCUSDT",
        "risk_usdt": risk_usdt,
        "leverage": leverage,
        "rr": rr,
        "grade": "A",
        "edge_multiple": 3.0,
    }


def _config():
    return {
        "risk": {
            "per_trade_pct": 0.0075,
            "max_open_risk_pct": 0.025,
            "daily_loss_halt_pct": 0.03,
            "max_leverage_linear": 20,
            "min_rr": 1.5,
        },
        "fees": {"min_edge_multiple_of_rt": 2.5},
    }


def test_gates_pass_normal():
    passed, reason = check_all_gates(
        _action(), _snapshot(equity=100.0), _config(), free_budget=5.0
    )
    assert passed, f"Expected pass but got: {reason}"


def test_gates_fail_on_daily_halt():
    snap = _snapshot(equity=100.0, daily_pnl=-4.0)  # > 3% loss
    passed, reason = check_all_gates(_action(), snap, _config(), free_budget=5.0)
    assert not passed
    assert "halt" in reason.lower() or "daily" in reason.lower()


def test_gates_fail_on_low_rr():
    act = _action(rr=0.8)  # below min_rr=1.5
    passed, reason = check_all_gates(act, _snapshot(), _config(), free_budget=5.0)
    assert not passed
