# 沪深300板块热度数据

## 数据源

- **hs300_stocks.csv** — AKShare `ak.index_stock_cons_csindex(symbol="000300")` 获取的最新成分股（300只）
- **chan_hs300_scan.csv** — 缠论全量扫描结果（333只→138买点→10中枢内）
- **chan_daily_report.md** — 每日自动生成的 markdown 分析日报

## 板块热度

板块热点使用通达信 easy-tdx 实时获取（概念+行业各15只）：
- `amount` 字段为元，需 /1e8 转亿
- `main_net_amount` 字段为主力净流入（元），同样需转亿
- `up_count` / `down_count` 为上涨/下跌家数

板块数据已整合到日报的"板块热点"章节。
