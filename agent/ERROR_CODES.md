# Bybit Error Codes — Agent Quick Fix Guide

When `retCode != 0`, use this table to fix without human intervention.

## Auth Errors

| retCode | Message | Fix |
|---|---|---|
| 10003 | Invalid api_key | Check `BYBIT_API_KEY` env var |
| 10004 | Error sign | Check `BYBIT_API_SECRET`, verify clock sync (`date` cmd) |
| 10005 | Permission denied | API key missing required permissions (set on Bybit dashboard) |
| 33004 | Api key expired | Renew API key on Bybit |

## Order Errors

| retCode | Message | Fix |
|---|---|---|
| 10001 | Param error | Check `--json-schema` for correct params |
| 110001 | Order not found | Order already filled or cancelled |
| 110003 | QTY below min | Check `bybit-cli market instruments-info --category linear --symbol SYMBOL` for minOrderQty |
| 110004 | Insufficient balance | Reduce qty, check wallet balance |
| 110007 | Insufficient margin | Lower leverage or reduce qty |
| 110009 | Too many orders | Cancel some: `bybit-cli order cancel-all --category linear --symbol X --yes` |
| 110011 | Price out of range | Use `orderType Market` or adjust limit price |
| 110013 | Cancel rejected | Order already filled |
| 110014 | reduceOnly — no position | No open position to reduce |
| 110017 | Position size exceeded | Reduce qty or close partial first |
| 110025 | TP/SL price invalid | TP must be above entry (long) or below (short) |
| 110043 | Set leverage not modified | Leverage already at that level, safe to ignore |

## Rate Limits

| retCode | Message | Fix |
|---|---|---|
| 10006 | Too many visits | Slow down, add `time.sleep(0.5)` between calls |
| 10016 | Service unavailable | Retry after 5s, check Bybit status |

## Position Errors

| retCode | Message | Fix |
|---|---|---|
| 130021 | Risk limit exceeded | Reduce position size or check risk tier |
| 130125 | Invalid side | Flip Buy/Sell |

## Recovery Procedure

```bash
# 1. Check what state we're in
bybit-cli position info --category linear --pretty
bybit-cli order realtime --category linear --pretty
bybit-cli account wallet-balance --accountType UNIFIED --pretty

# 2. If confused, cancel everything
bybit-cli order cancel-all --category linear --symbol BTCUSDT --yes

# 3. If emergency
bybit-cli kill-switch
```

## cli.nextSteps

Always check the `cli.nextSteps` field in the JSON response — it contains exact commands to unblock the situation automatically.

```bash
# Parse nextSteps from response
bybit-cli order create ... | python3 -c "
import sys, json
r = json.load(sys.stdin)
if r['retCode'] != 0:
    print('ERROR:', r['retMsg'])
    print('HINT:', r.get('cli', {}).get('hint', ''))
    for step in r.get('cli', {}).get('nextSteps', []):
        print('NEXT:', step)
"
```
