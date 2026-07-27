# 机构共识选股 (吸收自 fund-stock-picker)

## 双策略

### 动量型 (Momentum)
跟随聪明钱: 最近涨得好的基金在买什么
score = Σ(fund_rank_weight × holding_pct × fund_return)

### 共识型 (Consensus)  
多只基金共同重仓=机构共识
score = 基金数量 × 平均持仓% × 基金表现

## 与缠论框架整合
缠论(中枢+Buy) → 技术面 ✅
机构共识 → 资金面 🆕  
阿娇R1-R4 → 风控 ✅
XGBoost → 量化 ✅

## 参数参考
- 激进: sort_period=近1月, fund_top_n=20
- 稳健: sort_period=近1年, min_fund_count=5
- 大盘: min_fund_size=10亿
