# A股特色数据源接口 + 筹码分布 — 吸收自 myhhub/stock (InStock)

来源：https://github.com/myhhub/stock（InStock 股票系统，A股数据采集+技术分析）

本文件记录**免费直连的 A股特色数据源接口**（东财/同花顺），补充 a-share-market-analysis 数据层。

---

## 一、东方财富数据中心（datacenter-web.eastmoney.com）

统一入口：`https://datacenter-web.eastmoney.com/api/data/v1/get`

### 1. 龙虎榜明细（游资席位）
```python
url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
params = {
    "sortTypes": "1,-1",
    "reportName": "RPT_DAILYBILLBOARD_DETAILSNEW",
    "columns": "SECURITY_CODE,SECUCODE,SECURITY_NAME_ABBR,TRADE_DATE,EXPLAIN,CLOSE_PRICE,CHANGE_RATE,BILLBOARD_NET_AMT,BILLBOARD_BUY_AMT,BILLBOARD_SELL_AMT,BILLBOARD_DEAL_AMT,ACCUM_AMOUNT,DEAL_NET_RATIO,DEAL_AMOUNT_RATIO,TURNOVERRATE,FREE_MARKET_CAP,EXPLANATION,D1_CLOSE_ADJCHRATE,D2_CLOSE_ADJCHRATE,D5_CLOSE_ADJCHRATE,D10_CLOSE_ADJCHRATE,SECURITY_TYPE_CODE",
}
```
- 机构买卖统计：`reportName=RPT_ORGANIZATION_TRADE_DETAILS`（stock_lhb_jgmmtj_em）
- 机构专用统计：`reportName=RPT_BILLBOARD_TRADEDETAIL`（stock_lhb_jgstatistic_em）
- 龙虎榜行业营业部：`RPT_OPERATEDEPT_TRADE_DETAILS`

### 2. 大宗交易
```python
# 市场统计
'reportName': 'PRT_BLOCKTRADE_MARKET_STA'
# 每日明细
'reportName': 'RPT_DATA_BLOCKTRADE'
```

---

## 二、东方财富资金流向（push2.eastmoney.com）

```python
# 个股资金流向排名(5日/今日等)
url = "http://push2.eastmoney.com/api/qt/clist/get"
params = {
    "pn": 1, "pz": 5000, "po": 1, "np": 1,
    "fltt": 2, "invt": 2,
    "fid": "f62",  # 主力净流入
    "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",  # 沪深A股
    "fields": "f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205,f124",
}
```

---

## 三、同花顺涨停原因（zx.10jqka.com.cn）

```python
# 涨停原因列表(按日期)
url = f"http://zx.10jqka.com.cn/event/api/getharden/date/{date}/orderby/date/orderway/desc/charset/GBK/"
# 单只涨停原因详情
url = f"http://zx.10jqka.com.cn/event/harden/stockreason/id/{id}"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.138 Safari/537.36"}
```

用途：涨停≠买入（见 SKILL.md pitfall），涨停原因揭示是游资接力还是消息驱动。

---

## 四、筹码分布 CYQ 算法（scripts/cyq_chip.py）

A股特有的三角分布筹码模型。核心：每根K线在 [low,high] 区间按三角分布堆叠筹码（均价 avg=(O+C+H+L)/4 为峰值），换手率模拟筹码换手衰减。

```python
from cyq_chip import calc_cyq
r = calc_cyq(opens, closes, highs, lows, turnovers, crange=120, cyq_days=210)
# r['benefit_part']  获利盘比例(当前价下方筹码占比 0~1)
# r['avg_cost']      平均成本(50%筹码成本价) → 主力成本锚
# r['concentration_90'] 90%筹码集中度(越小越集中) → 主力控盘度
# r['price_range_90']   90%筹码价格区间 → 支撑/压力
```

### 筹码分布用法（与缠论互补）
| 指标 | 意义 | 操作含义 |
|---|---|---|
| benefit_part < 0.1 | 深度套牢盘 | 上方抛压重，反弹即减仓 |
| benefit_part > 0.9 | 几乎全获利 | 追高风险，警惕出货 |
| concentration_90 < 0.1 | 筹码高度集中 | 主力控盘，突破有效性高 |
| avg_cost 接近现价 | 筹码密集区 | 现价即主力成本，安全边际 |
| 现价 < avg_cost | 跌破主力成本 | 主力套牢，可能有自救/止损 |

### 数据源：换手率
筹码分布需要换手率。东财接口：`stock_individual_fund_flow_rank` 含 TURNOVERRATE；或从成交量/流通股本计算。新浪K线不含换手率，需东财补充。

---

## 五、其他可吸收数据

- **早盘/尾盘抢筹**（stock_cpbd.py）— 呼应 SKILL.md「早盘抢筹≠主力吸筹」分析
- **分红配股**（stock_fhps_em.py）— 分红除权日历
- **综合选股**（stock_selection.py）— 200+ 栏目自由组合（基本面/技术面/消息面/人气/行情）
- **技术指标**（calculate_indicator.py）— 32指标，公式与同花顺/通达信一致
