# 概率预测层 — 缠论结构的概率补充

> 来源: TradeHelper (github.com/Little-Pr1nce/TradeHelper) 评估, 2026-07-05
> 核心理念: 缠论给结构锚点 → 概率引擎给置信度量化

## 为什么需要概率层

缠论的输出是**确定性结构信号**(中枢/BSP/笔方向), 但不回答"这个三买历史上成功概率多少"。
概率引擎补充: 在当前位置, 找历史上最相似的K线状态 → 统计后续1/3/5日涨跌分布 → 输出概率。

两者结合 = 结构锚定 + 概率量化。

## TradeHelper forecast_engine 核心设计

### 特征(仅4个, 简洁)
- `momentum_5`: 5日收益率
- `momentum_20`: 20日收益率
- `trend_20`: 20日均线方向
- `volatility_20`: 20日波动率

### 模型候选
| 类型 | 参数 | 适用 |
|------|------|------|
| analog | neighbor_count=40/80/120 | 默认首选, 透明可复现 |
| logistic | regularization=0.05/0.20 | 快速, 需足够样本 |
| tree | max_depth=2, min_leaf=15/25 | 小样本下更稳定 |
| ensemble | neighbor+logistic混合 | 综合最优 |

### 输出
- `probability_up`: 上涨概率(1/3/5日)
- `expected_return`: 期望收益
- `confidence_interval`: 置信区间
- `sample_size`: 历史相似状态样本数

### 关键约束
- 样本<30时不输出(不编造伪概率)
- Champion晋升需walk-forward OOF验证
- 特征只用OHLCV派生(不看策略动作, 避免过拟合)

## 与缠论集成方案

```python
# 理想工作流:
chan_result = chan_analyze(...)  # 结构信号
prob_result = forecast_engine(close, horizons=(1,3,5))  # 概率信号

# 共振判断:
if chan_result.has_buy and prob_result.prob_up_5d > 0.60:
    signal = "强买入"  # 结构+概率双确认
elif chan_result.has_buy and prob_result.prob_up_5d < 0.40:
    signal = "弱买入"  # 结构看好但历史概率不支持
```

## 移植优先级

1. **analog模型**(最简单): 找历史上4特征欧氏距离最近的K个状态, 统计后续涨跌
2. **logistic模型**: sklearn直接调包
3. **ensemble**: analog+logistic加权混合

不需要TradeHelper完整系统 — 只需forecast_engine核心约200行。
