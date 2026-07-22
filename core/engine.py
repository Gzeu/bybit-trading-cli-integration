"""
Shared Trading Engine
Used by all strategies as base layer.
Provides: CLI wrapper, position sizing, ATR calc, logging, Telegram, error handling.

Changes vs previous version:
  - enter() accepts order_type / time_in_force / expiry_seconds
  - calc_qty() delegates to order_utils.calc_qty_net (fee-aware)
  - get_free_margin() helper: total_equity - position_margin_in_use
  - Limit orders include --price arg for bybit-cli
  - PostOnly / GTC / IOC / GoodTillDate fully wired through
"""
import subprocess, json, os, time, statistics, datetime, argparse, sys
from pathlib import Path

# --- Config ---
SYMBOL   = os.getenv("SYMBOL", "BTCUSDT")
CATEGORY = os.getenv("CATEGORY", "linear")
BYBIT_ENV = os.getenv("BYBIT_ENV", "testnet")
CAP_USD  = os.getenv("CAP_USD", "500")
MAX_RISK_PCT = float(os.getenv("MAX_RISK_PCT", "0.01"))  # 1% balance per trade
LEVERAGE = int(os.getenv("LEVERAGE", "5"))
LOG_DIR  = Path(os.getenv("LOG_DIR", "logs"))
LOG_DIR.mkdir(exist_ok=True)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")


# --- CLI wrapper with retry + error logging ---
def cli(*args, retries=2):
    for attempt in range(retries + 1):
        r = subprocess.run(["bybit-cli"] + list(args), capture_output=True, text=True)
        try:
            data = json.loads(r.stdout)
        except json.JSONDecodeError:
            log_error(f"JSON decode error: {r.stdout[:200]}")
            if attempt < retries:
                time.sleep(1)
                continue
            return {"retCode": -1, "retMsg": "JSON parse error", "result": {}}

        if data.get("retCode", -1) != 0:
            hint = data.get("cli", {}).get("hint", "")
            retry_ok = data.get("cli", {}).get("retry", False)
            log_error(f"CLI error {data['retCode']}: {data.get('retMsg')} | hint: {hint}")
            if retry_ok and attempt < retries:
                time.sleep(1.5)
                continue
        return data
    return {"retCode": -1, "retMsg": "Max retries exceeded", "result": {}}


# --- Market data ---
def get_klines(interval="60", limit=200, symbol=None, category=None):
    data = cli("market", "kline",
               "--category", category or CATEGORY,
               "--symbol", symbol or SYMBOL,
               "--interval", interval,
               "--limit", str(limit))
    candles = data.get("result", {}).get("list", [])
    return candles  # raw: [time, open, high, low, close, volume, turnover]

def closes(candles): return [float(c[4]) for c in candles]
def highs(candles):  return [float(c[2]) for c in candles]
def lows(candles):   return [float(c[3]) for c in candles]
def volumes(candles):return [float(c[5]) for c in candles]

def get_ticker(symbol=None, category=None):
    data = cli("market", "tickers",
               "--category", category or CATEGORY,
               "--symbol", symbol or SYMBOL)
    items = data.get("result", {}).get("list", [])
    return items[0] if items else {}

def get_balance():
    data = cli("account", "wallet-balance", "--accountType", "UNIFIED")
    try:
        return float(data["result"]["list"][0]["totalEquity"])
    except:
        return 0.0

def get_free_margin() -> float:
    """Return free margin = totalEquity - totalInitialMargin.

    This is the capital available to open new positions without
    touching margin already allocated to open trades.
    Falls back to get_balance() if field not available.
    """
    data = cli("account", "wallet-balance", "--accountType", "UNIFIED")
    try:
        info = data["result"]["list"][0]
        equity  = float(info.get("totalEquity", 0))
        im_used = float(info.get("totalInitialMargin", 0))
        return max(equity - im_used, 0.0)
    except:
        return get_balance()

def get_position(symbol=None, category=None):
    data = cli("position", "info",
               "--category", category or CATEGORY,
               "--symbol", symbol or SYMBOL)
    items = data.get("result", {}).get("list", [])
    if items and float(items[0].get("size", 0)) > 0:
        return items[0]
    return None

def get_funding_rate(symbol=None, category=None):
    ticker = get_ticker(symbol, category)
    return float(ticker.get("fundingRate", 0))


# --- Snapshot (used by llm/agent_loop.py) ---
def build_snapshot(symbol=None, category=None) -> dict:
    """Collect market + account state and return as a JSON-serialisable dict."""
    sym = symbol or SYMBOL
    cat = category or CATEGORY
    ts  = datetime.datetime.utcnow().isoformat() + "Z"

    ticker   = get_ticker(sym, cat)
    balance  = get_balance()
    free_margin = get_free_margin()
    position = get_position(sym, cat)
    candles  = get_klines(interval="60", limit=50, symbol=sym, category=cat)

    price      = float(ticker.get("lastPrice", 0))
    bid        = float(ticker.get("bid1Price", 0))
    ask        = float(ticker.get("ask1Price", 0))
    funding    = float(ticker.get("fundingRate", 0))
    volume_24h = float(ticker.get("volume24h", 0))
    price_24h_pct = float(ticker.get("price24hPcnt", 0))
    spread_pct = round((ask - bid) / price * 100, 4) if price else 0

    cl = closes(candles) if candles else []
    current_rsi   = round(rsi(cl), 2)     if len(cl) >= 15 else None
    current_atr   = round(atr(candles), 4) if len(candles) >= 15 else None
    current_ema20 = round(ema(cl, 20), 4)  if len(cl) >= 20 else None
    current_ema50 = round(ema(cl, 50), 4)  if len(cl) >= 50 else None
    current_zscore= round(zscore(cl), 4)   if len(cl) >= 50 else None

    regime = "unknown"
    if current_ema50 and price:
        regime = "bullish" if price > current_ema50 else "bearish"

    pos_summary = None
    if position:
        pos_summary = {
            "side":           position.get("side"),
            "size":           float(position.get("size", 0)),
            "entry_price":    float(position.get("avgPrice", 0)),
            "unrealised_pnl": float(position.get("unrealisedPnl", 0)),
            "liq_price":      float(position.get("liqPrice", 0)),
            "leverage":       float(position.get("leverage", LEVERAGE)),
        }

    snapshot = {
        "timestamp":      ts,
        "env":            BYBIT_ENV,
        "symbol":         sym,
        "category":       cat,
        "price":          price,
        "bid":            bid,
        "ask":            ask,
        "spread_pct":     spread_pct,
        "price_24h_pct":  price_24h_pct,
        "volume_24h":     volume_24h,
        "funding_rate":   funding,
        "balance_usdt":   round(balance, 4),
        "free_margin":    round(free_margin, 4),
        "max_risk_pct":   MAX_RISK_PCT,
        "leverage":       LEVERAGE,
        "indicators": {
            "rsi_14":    current_rsi,
            "atr_14":    current_atr,
            "ema_20":    current_ema20,
            "ema_50":    current_ema50,
            "zscore_50": current_zscore,
            "regime":    regime,
        },
        "open_position":      pos_summary,
        "kill_switch_active": False,
    }
    return snapshot


# --- Indicators ---
def ema_series(prices, period):
    k = 2 / (period + 1)
    result = [prices[0]]
    for p in prices[1:]:
        result.append(p * k + result[-1] * (1 - k))
    return result

def ema(prices, period):
    return ema_series(prices, period)[-1]

def atr(candles, period=14):
    h = highs(candles)
    l = lows(candles)
    c = closes(candles)
    trs = [max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])) for i in range(1, len(c))]
    return sum(trs[-period:]) / period

def rsi(closes_list, period=14):
    gains, losses = [], []
    for i in range(1, len(closes_list)):
        d = closes_list[i] - closes_list[i-1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    ag = sum(gains[-period:]) / period
    al = sum(losses[-period:]) / period
    if al == 0: return 100.0
    return 100 - (100 / (1 + ag/al))

def zscore(prices, lookback=50):
    w = prices[-lookback:]
    mean = statistics.mean(w)
    std  = statistics.stdev(w)
    return (prices[-1] - mean) / std if std > 0 else 0


# --- Position sizing ---
def calc_qty(stop_distance, risk_pct=None, balance=None, price=None):
    """Fee-aware fixed-fractional sizing.

    Delegates to order_utils.calc_qty_net so commission is always
    deducted from the risk budget.  Backward-compatible: existing
    callers that pass only stop_distance still work.
    """
    if balance is None:
        balance = get_balance()
    if price is None or price <= 0:
        # price unknown — fall back to legacy formula
        if balance <= 0 or stop_distance <= 0:
            return float(os.getenv("QTY", "0.01"))
        risk = balance * (risk_pct or MAX_RISK_PCT)
        return max(round(risk / stop_distance, 3), 0.001)
    from core.order_utils import calc_qty_net
    return calc_qty_net(
        stop_distance=stop_distance,
        balance=balance,
        risk_pct=risk_pct or MAX_RISK_PCT,
        price=price,
        maker=True,  # assume limit by default
    )

def calc_atr_stop(candles, side, atr_mult=1.5):
    """ATR-based stop: entry ± ATR_mult * ATR"""
    current_atr = atr(candles)
    price = closes(candles)[-1]
    if side == "Buy":
        return round(price - atr_mult * current_atr, 2)
    else:
        return round(price + atr_mult * current_atr, 2)


# --- Order execution ---
def set_leverage(leverage=None):
    lev = str(leverage or LEVERAGE)
    cli("position", "set-leverage",
        "--category", CATEGORY, "--symbol", SYMBOL,
        "--buyLeverage", lev, "--sellLeverage", lev, "--yes")

def close_position(pos=None):
    """Close existing position with Market IOC order."""
    if pos is None:
        pos = get_position()
    if pos is None:
        return
    close_side = "Sell" if pos["side"] == "Buy" else "Buy"
    size = pos["size"]
    result = cli("order", "create",
                 "--category", CATEGORY, "--symbol", SYMBOL,
                 "--side", close_side, "--orderType", "Market",
                 "--timeInForce", "IOC",
                 "--qty", str(size), "--reduceOnly", "true",
                 "--cap-usd", CAP_USD, "--yes")
    log_trade("CLOSE", close_side, float(size), 0, 0, result)
    return result


def enter(
    side: str,
    qty: float,
    stop_loss: float,
    take_profit=None,
    reason: str = "",
    order_type: str = "Limit",
    time_in_force: str = "PostOnly",
    expiry_seconds: int | None = None,
    limit_price: float | None = None,
):
    """Enter a position.

    order_type     : 'Limit' (default, maker fee) or 'Market' (taker fee)
    time_in_force  : 'PostOnly' | 'GTC' | 'IOC' | 'FOK' | 'GoodTillDate'
    expiry_seconds : if set + Limit order, uses GoodTillDate with this TTL
    limit_price    : required when order_type='Limit'; pass bid (Buy) or ask (Sell)
                     from current ticker.  If None, falls back to Market.
    """
    from core.order_utils import order_expiry_args

    # Guard: Limit requires a price
    if order_type == "Limit" and limit_price is None:
        log_info("[enter] limit_price not provided — falling back to Market/IOC")
        order_type, time_in_force = "Market", "IOC"

    # Close opposite position first
    pos = get_position()
    if pos and pos["side"] != side:
        log_info(f"Closing opposite {pos['side']} before entering {side}")
        close_position(pos)
        time.sleep(0.5)

    args = [
        "order", "create",
        "--category", CATEGORY, "--symbol", SYMBOL,
        "--side", side, "--orderType", order_type,
        "--qty", str(qty),
        "--stopLoss", str(stop_loss),
        "--slTriggerBy", "LastPrice",
        "--cap-usd", CAP_USD, "--yes",
    ]

    if order_type == "Limit" and limit_price is not None:
        args += ["--price", str(round(limit_price, 2))]

    # timeInForce + optional expiry
    args += order_expiry_args(order_type, time_in_force, expiry_seconds)

    if take_profit:
        args += ["--takeProfit", str(take_profit), "--tpTriggerBy", "LastPrice"]

    result = cli(*args)
    price = closes(get_klines(limit=1))[-1] if result.get("retCode") == 0 else 0
    log_trade("ENTER", side, qty, price, stop_loss, result, reason)
    alert(
        f"\u23f5 {order_type} {side} {SYMBOL} qty={qty} "
        f"sl={stop_loss} tp={take_profit or 'none'} "
        f"tif={time_in_force} | {reason}"
    )
    return result


# --- Logging ---
def _logline(level, msg):
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    log_file = LOG_DIR / f"agent_{datetime.date.today().strftime('%Y%m%d')}.log"
    with open(log_file, "a") as f:
        f.write(line + "\n")

def log_info(msg):  _logline("INFO",  msg)
def log_error(msg): _logline("ERROR", msg)

def log_trade(action, side, qty, price, sl, result, reason=""):
    ts = datetime.datetime.utcnow().isoformat()
    record = {
        "ts": ts, "action": action, "symbol": SYMBOL, "category": CATEGORY,
        "side": side, "qty": qty, "price": price, "sl": sl,
        "retCode": result.get("retCode"), "retMsg": result.get("retMsg"),
        "orderId": result.get("result", {}).get("orderId", ""),
        "reason": reason, "env": BYBIT_ENV
    }
    trade_log = LOG_DIR / "trades.jsonl"
    with open(trade_log, "a") as f:
        f.write(json.dumps(record) + "\n")


# --- Telegram ---
def alert(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return
    try:
        ts = datetime.datetime.utcnow().strftime("%H:%M UTC")
        text = f"*[BYBIT {BYBIT_ENV.upper()}]* {ts}\n{msg}"
        subprocess.run([
            "curl", "-s", "-X", "POST",
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            "-d", f"chat_id={TELEGRAM_CHAT}",
            "-d", "parse_mode=Markdown",
            "-d", f"text={text}"
        ], capture_output=True, timeout=5)
    except:
        pass


# --- Safety checks ---
def safety_check(max_daily_loss_pct=0.03):
    try:
        data = cli("position", "closed-pnl", "--category", CATEGORY, "--limit", "50")
        trades = data.get("result", {}).get("list", [])
        today = datetime.date.today().strftime("%Y%m%d")
        today_pnl = sum(float(t["closedPnl"]) for t in trades if t.get("updatedTime", "")[:8] == today)
        balance = get_balance()
        loss_pct = abs(today_pnl) / balance if balance > 0 and today_pnl < 0 else 0
        if loss_pct > max_daily_loss_pct:
            log_error(f"Daily loss {loss_pct:.2%} > {max_daily_loss_pct:.2%}. Activating kill-switch.")
            alert(f"\u26a0\ufe0f KILL-SWITCH: daily loss {loss_pct:.2%} exceeded threshold")
            cli("kill-switch")
            return False
        log_info(f"Safety OK | daily_pnl={today_pnl:.4f} USDT ({loss_pct:.2%}) | balance={balance:.2f}")
        return True
    except Exception as e:
        log_error(f"Safety check failed: {e}")
        return True


# --- CLI entrypoint ---
def _cli_main():
    parser = argparse.ArgumentParser(description="Trading Engine CLI")
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--json",     action="store_true")
    parser.add_argument("--action",   type=str)
    parser.add_argument("--symbol",   type=str, default=SYMBOL)
    parser.add_argument("--qty",      type=float, default=0.0)
    parser.add_argument("--strategy", type=str, default="none")
    parser.add_argument("--sl",       type=float, default=0.0)
    parser.add_argument("--tp",       type=float, default=0.0)
    args = parser.parse_args()

    if args.snapshot:
        snap = build_snapshot(symbol=args.symbol)
        print(json.dumps(snap, indent=2 if not args.json else None))
        return

    if args.action:
        action_map = {
            "open_long":      lambda: enter("Buy",  args.qty, args.sl, args.tp or None, args.strategy),
            "open_short":     lambda: enter("Sell", args.qty, args.sl, args.tp or None, args.strategy),
            "close_position": lambda: close_position(),
            "reduce_size":    lambda: close_position(),
        }
        fn = action_map.get(args.action)
        if fn:
            result = fn()
            print(json.dumps(result))
        else:
            print(json.dumps({"error": f"Unknown action: {args.action}"}))
            sys.exit(1)
        return

    parser.print_help()


if __name__ == "__main__":
    _cli_main()
