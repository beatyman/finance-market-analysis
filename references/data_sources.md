# AKShare 数据获取注意事项

## 重试机制（关键）

东财 API 有 IP 频率限制，不是封 IP。单次失败后等待 5s 重试即可——3 次尝试内必通。

```python
import akshare as ak, time

def retry(fn, n=3):
    for i in range(n):
        try:
            return fn()
        except Exception as e:
            if i < n-1:
                time.sleep(5 * (i+1))  # 5s, 10s
    return None

# 使用
df = retry(ak.stock_board_industry_name_em)  # 496 行业板块
df = retry(ak.stock_board_concept_name_em)   # 494 概念板块
```

## 可用的 AKShare 接口

- `stock_board_industry_name_em()` — 行业板块列表 + 实时行情
- `stock_board_concept_name_em()` — 概念板块列表
- `stock_board_industry_cons_em(symbol)` — 板块成分股
- `stock_board_industry_hist_em(symbol)` — 板块K线
- `get_cffex_rank_table(date, vars_list)` — 中金所持仓排名
- `get_rank_sum_daily(start, end, vars_list)` — 持仓变化趋势

## 腾讯资金流数据

`web.ifzq.gtimg.cn/appstock/app/board/index?code=sh000001` 返回的字段：
- `zllr` / `zllc`: 主力净流入/流出，单位：元
- `zljlr`: 主力净流入（净额），单位：元
- `cje`: 成交额，单位：元
- `d5` / `d20`: 5日/20日均值

**注意**：此接口返回的是板块指数级别数据，非板块全量资金流——用于判断方向和相对排名够用，但不能代表全市场主力资金。

## 数据源优先级

```
K线: Tencent(qfqday) → yfinance → AKShare → baostock
行情: Tencent(qt.gtimg.cn) → AKShare
板块: AKShare(direct+retry) → CSV → Tencent(个股推断)
期货: AKShare(CFFEX) + yfinance(COMEX)
宏观: yfinance(^TNX/DX-Y.NYB/CNY=X)
```

## K线格式差异

- 腾讯 A 股: `qfqday` 字段，6个元素 [日期,开,收,高,低,量]
- 腾讯港股: `day` 字段，需 `-L` 重定向，7个元素（最后一个是字典）
- yfinance: MultiIndex columns，需 `.ravel()` 或 `xs()`
- baostock: 返回 `datetime.date` 对象，需 `str()` 转换
