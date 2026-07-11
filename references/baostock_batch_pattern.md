# Baostock 共享连接批处理模式 (2026-07-11)

## 问题

`fetch_kline_a()` 每只股票调用一次 `bs.login()/bs.logout()` — 280次连接开销极大，全市场扫描超600秒。

## 修复

```python
# ❌ 慢: 280次login/logout
for code in stocks:
    data = fetch_kline_a(code)  # 内部 bs.login() → query → bs.logout()

# ✅ 快: 1次login，批量查询，1次logout
import baostock as bs
bs.login()
kline_cache = {}
for code, name in stocks:
    sym = 'sh.' + code if code.startswith('6') else 'sz.' + code
    rs = bs.query_history_k_data_plus(sym, ...)
    rows = []
    while rs.error_code == '0' and rs.next():
        rows.append(rs.get_row_data())
    if len(rows) >= 100:
        kline_cache[code] = (dates, opens, closes, highs, lows, vols)
bs.logout()
# → 280只股票 100秒完成
```

## 同时修改 data.py 优先级

`fetch_kline()` 默认源顺序改为: `['baostock','tencent','yfinance','akshare']`（baostock提到第一）。yfinance排在最后作为兜底。
