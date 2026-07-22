# Trading Types — Master Index

Bybit V5 supports 5 categories. Each has its own risk profile, margin model, and CLI params.

## Quick selector

| Type | Category | Margin | Best for |
|---|---|---|---|
| Spot | `spot` | None (own funds) | Accumulation, DCA, grid |
| Linear Futures | `linear` | USDT | Directional, leverage, most liquid |
| Inverse Futures | `inverse` | Coin-margined | Hedging coin holdings |
| Options | `option` | USDT | Volatility plays, hedging |
| Margin Trading | `spot` + margin | Borrowed USDT/coin | Leveraged spot |

## Files in this directory

- `spot_trading.md` — Spot buy/sell, limit orders, dust conversion
- `linear_futures.md` — USDT-margined perpetuals & delivery
- `inverse_futures.md` — Coin-margined (BTCUSD, ETHUSD)
- `options_trading.md` — Calls, puts, IV, Greeks via CLI
- `margin_trading.md` — Borrow, repay, isolated/cross margin
- `copy_trading.md` — Follow masters, manage copy positions

## Category param cheatsheet

```bash
--category spot      # Spot
--category linear    # USDT-margined futures/perps
--category inverse   # Coin-margined futures/perps
--category option    # Options
```
