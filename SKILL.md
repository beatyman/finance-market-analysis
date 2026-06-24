---
name: a-share-market-analysis
description: A股4454+港股780缠论全量分析 — chan.py买卖点→XGBoost 58维打分→SMC聪明钱→量价/板块/宏观共振
version: 3.1.0
author: Hermes
license: MIT
---

# 缠论多维量化分析系统

## 触发条件
- A股/港股分析、买卖点检测
- 全市场缠论扫描
- XGBoost模型训练
- 用户提到"缠论""chan""BSP""买点""评分"

## 十维分析流水线

按以下顺序输出：
1. **🌍 宏观环境前置** — 股指期货+DXY+美债+商品
2. 多源K线获取 (Tencent→yfinance→AKShare→baostock)
3. chan.py BSP/中枢提取
4. 58维特征+XGBoost评分 (AUC 0.662)
5. 缠论知识库确认 (chanstock语义搜索)
6. SMC聪明钱视角 (Order Block/Liquidity)
7. 量价分析 (放量/缩量背离)
8. 板块定位+实时热度

## 入口

```bash
cd scripts
python3 analyze.py 002475         # A股
python3 analyze.py hk00700        # 港股
python3 analyze.py --scan         # A股全市场
python3 analyze.py --scan --market hk --min-score 70
python3 train.py --stocks 27      # 训练XGBoost
```

## 输出格式

宏观前置 → 个股分析:
```
🌍 宏观: [期货/美元/美债/商品]
─ 个股分析 ─ [BSP] [XGBoost] [知识库] [SMC] [量价] [板块]
```

## 数据源限制

**可用(服务器)**: 腾讯qt/ifzq, yfinance, baostock, AKShare(CFFEX期货)
**不可用(IP被东财封)**: AKShare东财板块, tushare, 同花顺/通达信
**Windows辅助**: 用户Windows机可跑AKShare东财数据, scp同步

## 核心模块

- `analyze.py` — 主入口
- `data.py` — 4源回退, 自动截取250根K线
- `scorer.py` — 58维特征(BSP+MACD+布林+ADX+量+笔段背驰)
- `chan_kb.py` — 知识库+语义搜索确认
- `smc_insight.py` — SMC聪明钱
- `sector_heat.py` — 板块热度(腾讯行情推断)
- `volume_sector.py` — 量价+板块映射
- `macro.py` — 美债/DXY/汇率
- `futures_analysis.py` — COMEX期货chan分析
- `futures_sentiment.py` — CFFEX持仓情绪
- `train.py` — XGBoost训练(直接使用A股核心代码)

## Gotchas

1. 多源K线可能跨多年 → data.py自动截取最近250根
2. yfinance单股返回MultiIndex列 → `.ravel()`展开
3. BSP仅保留最近信号 → 历史大结构不干扰
4. 腾讯K线需 -L 跟随重定向
5. 港股代码在sector_heat中需hk前缀识别
