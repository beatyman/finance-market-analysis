---
name: a-share-market-analysis
description: A股4454+港股780缠论全量分析：chan.py买卖点 → XGBoost 58维打分 → 量价/板块/宏观/期货多维共振。支持单股/全市场扫描。零外部依赖(chanpy内嵌)。
version: 3.1.0
author: Hermes
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [a-share, hk-stock, chan, trading, bsp, scoring, xgboost, macro]
---

# 缠论·多维度分析 v3.1

chan.py 买卖点 + XGBoost 58维评分 + 十维共振

## 快速使用

```bash
cd ~/.hermes/skills/a-share-market-analysis/scripts
python3 analyze.py 002475          # 立讯精密
python3 analyze.py hk00700         # 腾讯控股
python3 analyze.py --scan --min-score 70  # A股全量≥70分
```

## 十维分析流水线

```
🌍 宏观环境 (股指期货/美元/美债/商品)
  └─ 个股分析
      ├── 数据获取 (Tencent行情 + yfinance K线)
      ├── 缠论结构 (chan.py BSP/中枢)
      ├── 58维评分 (XGBoost训练模型)
      ├── 知识库确认 (chanstock rules/workflow)
      ├── SMC聪明钱 (OpenMobius 665概念)
      ├── 量价分析 (放量/缩量背离)
      ├── 板块定位 + 实时热度 🆕
      └── 最终信号 (Buy/Sell/Hold + 目标 + 风险)
```

## XGBoost训练

```bash
python3 train.py --stocks 50 --years 3
# → models/chan_xgb_56d.pkl (AUC 0.662, 58维特征)
```

## 数据源 (多源自动回退)

| 数据 | 优先级 | 说明 |
|---|---|---|
| A股行情 | 腾讯 qt.gtimg.cn | 批量实时行情(唯一选择) |
| 港股行情 | 腾讯 qt.gtimg.cn | hk前缀 |
| K线 | Tencent → yfinance → AKShare → baostock | 自动回退，取最后250根 |
| 股指期货 | AKShare | CFFEX持仓排名 |
| 宏观因子 | yfinance | 美债/美元/汇率 |
| 商品期货 | yfinance | COMEX黄金/白银/铜 |

## 注意事项

- A股K线: qfqday字段(腾讯ifzq)
- 港股K线: day字段，需要-L重定向
- yfinance单股下载返回MultiIndex，需`.ravel()`
- chan.py Bi对象API: bi.begin_klc.low (不是.bi.begin_klc.klc.low)
- **baostock日期**: 返回datetime.date对象，需`str()`转换再`.split('-')`
- **250根K线限制**: 数据获取层自动截取最后250根，过多K线导致缠论结构失真(153笔/15中枢压倒近期信号)
- 全量扫描: 不分涨跌，全部分析，买/卖/观望三信号
- 宏观环境优先展示，再进入个股细节
- **多源回退**: Tencent → yfinance → AKShare → baostock，任意源可用即止

## 模块架构

```
scripts/
├── analyze.py           主入口(单股/扫描/10维整合)
├── data.py              数据源(Tencent+yfinance)
├── chan_engine.py        chan.py BSP/ZS提取
├── scorer.py             58维特征提取+打分
├── chan_kb.py            缠论知识库确认
├── smc_insight.py        SMC聪明钱视角
├── volume_sector.py      量价分析+板块定位
├── sector_heat.py        板块实时热度 🆕
├── futures_analysis.py   商品期货联动
├── futures_sentiment.py  股指期货持仓情绪
├── macro.py              宏观因子(美债/美元/汇率)
└── train.py              XGBoost 58维训练器
```

## 评分模型

v3.1 升级到58维（对齐chan-model-xgb V2）:
- 12 BSP one-hot + 6 动量 + 5 MA偏离 + 5 MACD
- 2 布林带 + 3 波动率 + 2 RSI + 2 ADX  
- 2 量价 + 5 笔特征 + 6 中枢特征 + 5 段/背驰/多级别
- AUC: 30维 0.626 → 58维 0.662 (+5.8%)
