# Strategy Decision Tree

Use this to pick the right strategy without guessing.

```
START
  │
  ├── Is funding rate > 0.01%?  ────────────────── YES → funding_arb.py
  │
  ├── Run regime_detection.py
  │     │
  │     ├── VOLATILE ─────────────────── STAY FLAT + kill-switch
  │     │
  │     ├── SIDEWAYS
  │     │     ├── Range tight? ───────── YES → grid_trading.py
  │     │     ├── Z-score ±2? ───────── YES → mean_reversion.py
  │     │     └── BB touch? ─────────── YES → bollinger_bands.py
  │     │
  │     ├── BULL
  │     │     ├── ADX > 25? ─────────── YES → adx_trend_filter.py
  │     │     ├── MTF aligned? ──────── YES → multi_timeframe.py
  │     │     ├── EMA cross? ────────── YES → trend_follow.py
  │     │     └── Default ────────────── supertrend.py
  │     │
  │     └── BEAR
  │           ├── ADX > 25? ─────────── YES → adx_trend_filter.py (short)
  │           ├── PSAR flip? ────────── YES → parabolic_sar.py
  │           └── Default ────────────── trend_follow.py (short)
  │
  ├── OI spike detected? ─────────────── YES → open_interest_spike.py
  │
  ├── Wick hunt on 15m? ──────────────── YES → liquidation_hunt.py
  │
  └── Long-term accumulation? ─────────── YES → dca_accumulation.py
```

## Confidence scoring (run before entry)

Before placing any order, score your signal:

| Check | Points |
|---|---|
| Regime confirms direction | +2 |
| MTF aligned (all 3 TF) | +2 |
| ADX > 25 | +1 |
| Volume above average | +1 |
| OI increasing in direction | +1 |
| No major news/event risk | +1 |
| Funding rate neutral | +1 |

**Score ≥ 6 → full size. Score 4-5 → half size. Score < 4 → skip.**
