# 实时买入清单 Excel 模板

用腾讯实时行情+baostock K线生成，替代yfinance延迟数据。

## 工作流

```python
# 1. 腾讯实时行情
url = 'http://qt.gtimg.cn/q=sz002475,sh603920,sz300033'
# code = p[2], name = p[1], price = p[3], change% = p[32]

# 2. baostock K线
bs.login()
rs = bs.query_history_k_data_plus(sym, 'date,open,high,low,close,volume', ...)
# 替换最新收盘价为实时价: C[-1] = live_px

# 3. chan.py + scorer分析

# 4. 输出Excel: /root/buy_list_live.xlsx
# 列: 代码/名称/实时价/涨跌%/信号/评分/年涨%/中枢/位置/买入/止损/TP1/TP2/R:R/MA60/量比
```

## 模板文件

`/root/buy_list_live.xlsx` — 上次生成的实时买入清单（腾讯行情+baostock，5只中枢内买点）
