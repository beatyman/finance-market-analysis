# A股全栈数据源速查 (吸收自 a-stock-data V3.4.0)

## 优先级原则
mootdx/腾讯（不封IP） > 东财（独有数据，内置限流≥1s+抖动）

## 十层架构速查

### 行情层 — mootdx + 腾讯
```python
# K线 (mootdx, 优先, 不复权)
bars(symbol='000001', frequency='D', count=100)
# 五档盘口 (腾讯)
# 指数/ETF (腾讯 qt.gtimg.cn)
```

### 研报层 — 东财 + 同花顺 + iwencai
- 个股研报: `eastmoney_reports(code)`
- 行业研报: `eastmoney_industry_reports(qType=1)`
- 一致预期: `full_valuation(code)` → PE_fwd/PEG

### 资金面 — 东财 datacenter + push2
- 融资融券: margin trading (两融余额)
- 大宗交易: block trades
- 北向资金: sgt 分钟/日序列 (HKEX 官方优先)
- 股东户数: shareholder count

### 龙虎榜 — 东财 + 同花顺
- 东财龙虎榜: daily list + detail
- 全市场龙虎榜: 所有上榜席位

### 公告层 — 巨潮 cninfo
- 全量沪深北公告 (动态orgId映射)

### 打板层 — 东财 push2ex + 同花顺
- 涨停/炸板/跌停/昨涨停四池
- 涨停原因题材 + 封板成功率
- 打板情绪: 炸板率 + 连板梯队

### ETF期权层 — 新浪 hq.sinajs
- T型报价 + 希腊字母(Greeks) + 隐含波动率(IV)

### 舆情互动
- 互动易问答 + 同花顺热榜 + 东财人气榜

## 备用源降级 (主源被封时)
| 场景 | 备胎 |
|------|------|
| 公告 | 深交所官方 + 东财 |
| 龙虎榜 | 沪深交易所官方 |
| 资金流 | 新浪 |
