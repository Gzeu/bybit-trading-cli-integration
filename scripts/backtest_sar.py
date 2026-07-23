#!/usr/bin/env python3
"""
backtest_sar.py — Simple SAR backtest on historical Bybit klines

Fetches historical OHLCV data and simulates SAR flip entries/exits.
Outputs: win_rate, avg_rr, expectancy, equity curve to logs/backtest_SYMBOL_TF.csv

Usage:
    python scripts/backtest_sar.py --symbol BTCUSDT --tf 5 --limit 1000
    python scripts/backtest_sar.py --symbol ETHUSDT --tf 15 --limit 2000
"""

import argparse
import csv
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skills.bybit_account_commander.src.sar_trend import compute_sar, compute_ema, compute_adx
from skills.bybit_account_commander.src.fees import compute_net_pnl


def fetch_klines_csv(symbol: str, tf: str, limit: int) -> list[dict]:
    """
    Fetch klines from Bybit public API (no auth needed).
    Returns list of {open, high, low, close, volume, ts}
    """
    try:
        import requests
    except ImportError:
        print("pip install requests")
        sys.exit(1)

    url = "https://api.bybit.com/v5/market/kline"
    params = {"category": "linear", "symbol": symbol,
              "interval": tf, "limit": min(limit, 1000)}
    resp = requests.get(url, params=params, timeout=15)
    data = resp.json()
    bars = data.get("result", {}).get("list", [])
    bars = list(reversed(bars))  # oldest first
    return [
        {
            "ts": int(b[0]),
            "open": float(b[1]),
            "high": float(b[2]),
            "low": float(b[3]),
            "close": float(b[4]),
            "volume": float(b[5]),
        }
        for b in bars
    ]


def run_backtest(
    bars: list[dict],
    af_start: float = 0.02,
    af_step: float = 0.02,
    af_max: float = 0.20,
    risk_pct: float = 0.0075,
    initial_equity: float = 100.0,
    fee_rate: float = 0.00055,
) -> dict:
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    closes = [b["close"] for b in bars]

    sar_vals = compute_sar(highs, lows, af_start, af_step, af_max)
    ema50 = compute_ema(closes, 50)

    equity = initial_equity
    trades = []
    position = None  # {side, entry, sl, qty}
    equity_curve = []

    for i in range(55, len(bars)):
        price = closes[i]
        sar = sar_vals[i]
        ema = ema50[i] if i < len(ema50) else None

        is_long = price > sar
        was_long = closes[i - 1] > sar_vals[i - 1]

        # SAR flip detection
        flip = is_long != was_long

        # Close existing position on flip
        if position and flip:
            side = position["side"]
            entry = position["entry"]
            qty = position["qty"]
            gross = (price - entry) * qty if side == "BUY" else (entry - price) * qty
            fee = price * qty * fee_rate * 2  # RT fee
            net = gross - fee
            equity += net
            trades.append({
                "i": i, "side": side, "entry": entry, "exit": price,
                "gross": gross, "fee": fee, "net": net, "equity": equity,
            })
            position = None

        # Open new position on flip (if EMA aligned)
        if flip and ema:
            new_side = "BUY" if is_long else "SELL"
            # EMA filter
            if new_side == "BUY" and price < ema:
                equity_curve.append(equity)
                continue
            if new_side == "SELL" and price > ema:
                equity_curve.append(equity)
                continue

            sl = sar
            dist = abs(price - sl)
            if dist == 0:
                equity_curve.append(equity)
                continue

            risk_usdt = equity * risk_pct
            qty = risk_usdt / dist
            position = {"side": new_side, "entry": price, "sl": sl, "qty": qty}

        equity_curve.append(equity)

    # Stats
    if not trades:
        return {"total": 0, "equity_curve": equity_curve}

    wins = [t for t in trades if t["net"] > 0]
    losses = [t for t in trades if t["net"] <= 0]
    win_rate = len(wins) / len(trades)
    avg_win = sum(t["net"] for t in wins) / len(wins) if wins else 0
    avg_loss = abs(sum(t["net"] for t in losses) / len(losses)) if losses else 0
    expectancy = win_rate * avg_win - (1 - win_rate) * avg_loss
    total_return = (equity - initial_equity) / initial_equity * 100

    return {
        "total": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 4),
        "avg_win": round(avg_win, 4),
        "avg_loss": round(avg_loss, 4),
        "expectancy": round(expectancy, 4),
        "total_net_pnl": round(equity - initial_equity, 4),
        "total_return_pct": round(total_return, 2),
        "final_equity": round(equity, 4),
        "equity_curve": equity_curve,
        "trades": trades,
    }


def save_results(result: dict, symbol: str, tf: str, log_dir: str = "logs") -> None:
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, f"backtest_{symbol}_{tf}.csv")
    trades = result.get("trades", [])
    if not trades:
        return
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["i", "side", "entry", "exit",
                                                "gross", "fee", "net", "equity"])
        writer.writeheader()
        writer.writerows(trades)
    print(f"  Saved: {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--tf", default="5")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--equity", type=float, default=100.0)
    parser.add_argument("--risk-pct", type=float, default=0.0075)
    parser.add_argument("--log-dir", default="logs")
    args = parser.parse_args()

    print(f"\nFetching {args.limit} bars for {args.symbol} TF={args.tf}...")
    bars = fetch_klines_csv(args.symbol, args.tf, args.limit)
    print(f"Got {len(bars)} bars. Running backtest...")

    result = run_backtest(
        bars,
        initial_equity=args.equity,
        risk_pct=args.risk_pct,
    )

    print()
    print("=" * 50)
    print(f"  BACKTEST: {args.symbol} TF={args.tf}m")
    print("=" * 50)
    if result["total"] == 0:
        print("  No trades generated.")
        return
    print(f"  Trades         : {result['total']}")
    print(f"  Wins / Losses  : {result['wins']} / {result['losses']}")
    print(f"  Win rate       : {result['win_rate']*100:.1f}%")
    print(f"  Avg win        : +{result['avg_win']:.4f} USDT")
    print(f"  Avg loss       : -{result['avg_loss']:.4f} USDT")
    print(f"  Expectancy     : {result['expectancy']:.4f} USDT/trade")
    print(f"  Total net PnL  : {result['total_net_pnl']:.4f} USDT")
    print(f"  Total return   : {result['total_return_pct']:.2f}%")
    print(f"  Final equity   : {result['final_equity']:.4f} USDT")
    print("=" * 50)
    print()

    save_results(result, args.symbol, args.tf, args.log_dir)


if __name__ == "__main__":
    main()
