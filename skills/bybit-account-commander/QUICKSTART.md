# Quick Start — Bybit Account Commander

## 1. Install dependencies
```bash
pip install -r requirements.txt
```

## 2. Set API keys
```bash
export BYBIT_API_KEY=your_key_here
export BYBIT_API_SECRET=your_secret_here
```

> ⚠️ Keys must have **read + trade** permissions only. Never enable withdraw.

## 3. Create your config
```bash
cp skills/bybit-account-commander/config.default.yaml config.yaml
```

Edit `config.yaml`:
```yaml
env: testnet          # start on testnet!
autonomous: false     # NEVER true until BRIEF looks correct
```

## 4. Testnet dry-run (single cycle)
```bash
python main.py --config config.yaml --once
```

Check the COMMANDER BRIEF output:
- Equity, available, FUND shown correctly?
- Fee rates populated?
- MMR/IMR reasonable?
- Sleeves target USDT makes sense?

## 5. Testnet loop
```bash
python main.py --config config.yaml --interval 300
```

Watch `logs/commander.jsonl` for cycle events:
```bash
tail -f logs/commander.jsonl | python -m json.tool
```

## 6. Production checklist before mainnet

- [ ] Testnet BRIEF looks correct for ≥5 cycles
- [ ] SAR signals match what you see on chart
- [ ] Fee rates match Bybit dashboard
- [ ] SL is being set on every position
- [ ] Gate blocks are firing correctly (not skipping filters)
- [ ] `autonomous: false` first on mainnet until RECOMMEND cards look right
- [ ] Set `config.yaml env: mainnet`
- [ ] Run `python main.py --config config.yaml --once` on mainnet
- [ ] Verify COMMANDER BRIEF with real balance
- [ ] Only then set `autonomous: true` + confirm `YES I UNDERSTAND`

## 7. Key risk parameters

| Param | Default | Meaning |
|---|---|---|
| `risk.per_trade_pct` | 0.75% | Max risk per SAR trade |
| `risk.max_open_risk_pct` | 2.5% | Max total open risk |
| `risk.daily_loss_halt_pct` | 3% | Hard stop for the day |
| `risk.max_leverage_linear` | 20x | Hard leverage cap |
| `fees.min_edge_multiple_of_rt` | 2.5x | Min edge vs round-trip fee |
| `sleeves.reserve_pct` | 30% | Never-touch buffer |

## 8. Directory structure

```
bybit-trading-cli-integration/
├── main.py                          ← entry point
├── config.yaml                      ← your config (gitignored)
├── logs/commander.jsonl             ← structured cycle logs
└── skills/bybit-account-commander/
    ├── SKILL.md                     ← agent brain spec
    ├── QUICKSTART.md                ← this file
    ├── config.default.yaml          ← default params
    ├── policies/
    │   ├── small_account.yaml
    │   └── production.yaml
    └── src/
        ├── commander_loop.py        ← main orchestrator
        ├── snapshot.py              ← account snapshot
        ├── allocator.py             ← sleeve allocator
        ├── sleeves.py               ← portfolio map
        ├── sar_trend.py             ← SAR + EMA + ADX
        ├── fees.py                  ← fee model
        ├── gates.py                 ← risk gates
        ├── mmr_guard.py             ← MMR guard
        ├── brief.py                 ← COMMANDER BRIEF
        ├── position_manager.py      ← adopt + SL guard + TP mgmt
        ├── execution/
        │   ├── router.py            ← order router
        │   ├── entry_policy.py      ← market vs limit
        │   └── profit_skim.py       ← perp → spot skim
        └── adapters/
            └── bybit_v5.py          ← pybit wrapper
```
