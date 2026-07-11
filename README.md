# 缠论多维量化分析系统

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> **缠论 + 双XGBoost + 三维评分 + 风控计划 + 宏观因子 = 六维共振选股**

全自动 A 股 / 港股缠论买卖点扫描系统。从数据获取到信号输出，一条命令完成全维度分析。

---

## ✨ 核心功能

| 功能 | 说明 |
|---|---|
| 🔍 全市场扫描 | A 股沪深300 300只，自动筛选买卖点 |
| 📐 缠论结构分析 | chan.py 引擎：笔/段/中枢/BSP 买卖点 |
| 🤖 双XGBoost打分 | 旧模型(56维) + 新模型300s(58维 AUC 0.717, 41K样本) |
| 📊 三维综合评分 | 技术40% + 基本面30% + 消息面30% → 仓位建议 |
| 🎯 风控计划 | 止损/仓位/入场区规则 + 风控过滤器 |
| 📈 宏观因子 | 股指期货持仓 + 美债收益率 + 北向资金 + 黄金/美元 |
| 💹 港股沽空 | 5只核心港股沽空率日跟踪 |

---

## 🧩 增强工具箱 (enhanced_tools.py)

17 模块 · ~1730行：

| 模块 | 功能 | 来源 |
|------|------|------|
| 1-3 | V4.5经验评分 | 自研 |
| 4-6 | G/Z/K/S评分 | 自研 |
| 7-9 | 信号衰减/连续因子/主线评分 | 自研 |
| 10 | 13项自检Gate | 自研 |
| 11 | K线形态(高紧旗/洗盘/海龟) | Sequoia-X |
| 12 | 北向资金(东财API) | chanlunStockAnalysis |
| 13 | K线多源回退(mootdx/腾讯) | chanlunStockAnalysis |
| 14 | 三维综合评分 | chanlun-quant |
| 15 | 风控过滤器 | chanlun-quant |
| 16 | MACD背驰6条件检查 | yanwuyou/chanlun-stock-analyzer |
| 17 | 风控计划(止损/仓位) | chanlun-trade-signal |
| 🥇 商品期货联动 | COMEX 黄金/白银/铜，chan.py 缠论分析 |
| 📈 板块热度 | 实时板块涨跌 + 资金轮动监测 |
| 📉 量价分析 | 放量/缩量检测，主力吸筹/出货识别 |
| 📚 知识库确认 | chanstock 缠论经典知识库 + 语义搜索验证 |
|| 🎯 多源数据 | Tencent / yfinance / AKShare / baostock 自动回退 |
|| 🔥 热点板块扫描 | 29个科技主题，117只核心标的，每日一键扫描 |

---

## 🚀 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/beatyman/finance-market-analysis.git
cd finance-market-analysis

# 安装依赖
pip install yfinance numpy pandas openpyxl xgboost scikit-learn akshare baostock

# 训练模型（可选，已包含预训练模型）
cd scripts && python3 train.py --stocks 27 --years 3
```

### 单股分析

```bash
cd scripts

# A 股
python3 analyze.py 002475     # 立讯精密
python3 analyze.py 601899     # 紫金矿业

# 港股
python3 analyze.py hk00700    # 腾讯控股
python3 analyze.py hk09988    # 阿里巴巴
```

### 全市场扫描

```bash
# A 股全量扫描（约 30 分钟）
python3 analyze.py --scan

# 港股全量扫描
python3 analyze.py --scan --market hk

# 仅显示高评分（≥70 分）
python3 analyze.py --scan --min-score 70
```

### 模型训练

```bash
# 用核心 27 只股票训练
python3 train.py --stocks 27 --years 3

# 模型自动保存到 ../models/chan_xgb_56d.pkl
```

### 热点板块批量扫描 🆕

```bash
# 每日一键扫描 117 只核心科技股（29 个主题板块）
python3 hot_scan.py

# 输出按主题分组的缠论分析结果 + 买入标的汇总
```

股票池: `references/hot_stocks.csv` — 覆盖半导体/光模块/PCB/存储/机器人/AI等 29 个板块

---

## 📊 输出示例

```
============================================================
缠论多维度分析: 002475
============================================================

🌍 宏观环境:
  📈 股指期货: 偏多
  💵 美元: DXY 101.5 (强势)
  📊 美债10Y: 4.45% (中性)
  🇨🇳 USD/CNY: 6.80
  🥇 商品: 黄金 Buy-一买 -6.3% | 白银 Buy-二买 -13.2% | 铜 Sell-一卖 -5.6%

─ 个股分析 ─
[1/3] chan.py 结构分析...
  BSP: Buy-中枢内买点 | 中枢: 53~61,67~78 | 位置: 内 | Bi:17 ZS:2
[2/3] XGB 56维特征提取+打分...
  📦 已加载训练模型 (XGBoost)
  评分: 70/100
[3/3] 缠论知识库确认...

📊 最终分析:
  标的: 002475 (¥73)
  方向: 买入 | 信号: 2s | 评分: 70/100
  风险: 低 | 盈利预期: +6.8% (目标 ¥78)
  🧠 SMC视角: SMC辅助但需更多确认
  📊 量价: 量价正常 (vol_ratio=1.2x)
  📈 板块: 消费电子/连接器 → 消费电子
  🔥 板块热度: 🔥 板块领涨 +2.8% (100%↑)
  ✅ 确认: 中枢内买点 — 标准二买/三买形态
```

---

## 🏗️ 架构

```
finance-market-analysis/
├── SKILL.md                    # Hermes Skill 元信息
├── scripts/
│   ├── analyze.py              # 主入口 — 单股分析 + 全市场扫描
│   ├── data.py                 # 多源数据层（Tencent/yfinance/AKShare/baostock）
│   ├── chan_engine.py          # chan.py BSP/中枢提取
│   ├── scorer.py               # 58维特征提取 + XGBoost打分
│   ├── chan_kb.py              # 缠论知识库确认（规则+语义搜索）
│   ├── smc_insight.py          # SMC聪明钱视角分析
│   ├── macro.py                # 宏观因子（美债/美元/汇率）
│   ├── futures_analysis.py     # COMEX商品期货分析
│   ├── futures_sentiment.py    # CFFEX股指期货持仓
│   ├── sector_heat.py          # 板块热度引擎
│   ├── volume_sector.py        # 量价分析 + 板块映射
│   ├── train.py                # XGBoost训练器
│   ├── chanlun_kb_search.py    # chanstock语义搜索
│   ├── chanlun_kb_eval.py      # 知识库评估
│   └── chanlun_kb_report.py    # 可视化报告
├── chanpy/                     # chan.py核心引擎（内嵌，零外部依赖）
├── references/
│   ├── a_stock_codes.csv       # 4454 A股代码
│   ├── hk_stock_codes.csv      # 780 港股代码
│   ├── chan_kb/                # 缠论知识库（chanstock-skill）
│   └── smc_kb/                 # SMC/ICT概念库（OpenMobius）
├── models/
│   └── chan_xgb_56d.pkl        # 预训练XGBoost模型（AUC 0.662）
└── requirements.txt
```

---

## 🔬 十维分析维度

| # | 维度 | 模块 | 数据源 |
|---|---|---|---|
| 1 | 缠论结构 | `chan_engine.py` | chan.py BSP/中枢 |
| 2 | XGBoost 打分 | `scorer.py` | 58维特征模型 |
| 3 | 知识库确认 | `chan_kb.py` | chanstock 语义搜索 |
| 4 | SMC 聪明钱 | `smc_insight.py` | 665概念知识库 |
| 5 | 期货持仓 | `futures_sentiment.py` | CFFEX AKShare |
| 6 | 商品联动 | `futures_analysis.py` | COMEX yfinance |
| 7 | 宏观因子 | `macro.py` | 美债/美元/汇率 |
| 8 | 量价分析 | `volume_sector.py` | 放量/缩量检测 |
| 9 | 板块定位 | `volume_sector.py` | 行业映射 |
| 10 | 板块热度 | `sector_heat.py` | 腾讯实时行情 |

---

## 🎯 评分模型

### 特征维度（58 维）

| 类别 | 数量 | 示例 |
|---|---|---|
| BSP 信号 | 12 | bsp_buy_type1, bsp_sell_type2s... |
| 价格动量 | 6 | price_return_1/3/5/10, range... |
| 均线偏离 | 5 | ma_5/10/20/60_dist, ma_cross_5_20 |
| MACD | 5 | macd_value, macd_cross, macd_hist... |
| 布林带 | 2 | boll_pct_b, boll_width |
| 波动率 | 3 | atr_norm, volatility_5/10, vol_ratio |
| RSI | 2 | rsi, rsi_divergence |
| ADX | 2 | adx, trend_strength |
| 成交量 | 2 | volume_zscore, volume_ratio_ma |
| 缠论结构 | 17 | bi_slope, zs_width, divergence... |

### 训练性能

| 训练集 | 样本 | 特征 | AUC |
|---|---|---|---|
| 港股 50 只 | 2,438 | 30维 | 0.656 |
| 核心 27 只 | 2,006 | 30维 | 0.626 |
| **核心 27 只** | 2,006 | **58维** | **0.662** ✅ |

---

## 🔗 数据源

| 数据源 | 优先级 | 用途 | 限制 |
|---|---|---|---|
| 腾讯 (qt.gtimg.cn) | 1 | 实时行情 + K线 | 需国内网络 |
| yfinance | 2 | K线 + 宏观 | 免费，每日限频 |
| AKShare | 3 | 期货持仓 + K线 | 部分接口需国内 |
| baostock | 4 | K线 | 免费，无限制 |

所有数据源配置在 `data.py` 中，支持自动回退。

---

## 🌐 外部知识库

- **[fpyluck/chanstock-skill](https://github.com/fpyluck/chanstock-skill)** — 缠论知识库 + 语义搜索引擎
- **[MobiusQuant/OpenMobius-skill](https://github.com/MobiusQuant/OpenMobius-skill)** — SMC/ICT 聪明钱概念库（665 概念 + 1246 案例）
- **[bambuo/chan-model-xgb](https://github.com/bambuo/chan-model-xgb)** — chan.py XGBoost 特征&训练框架
- **[Vespa314/chan.py](https://github.com/Vespa314/chan.py)** — 缠论核心技术引擎

---

## 📄 License

MIT
