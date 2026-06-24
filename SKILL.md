---
name: a-share-market-analysis
description: A股4454+港股780缠论全量分析：chan.py买卖点 → XGBoost 58维打分 → 量价/板块/宏观/SMC/知识库多维度共振。支持单股分析/全市场扫描。
version: 3.2.0
author: Hermes
license: MIT
platforms: [linux, windows]
metadata:
  hermes:
    triggers:
      - "分析.*股票"
      - "缠论.*分析"
      - "板块.*热度"
      - "scan.*market"
      - "train.*model"
    toolsets: [terminal, file, web, skills]
    memory: "skill:a-share-market-analysis"
  dependencies:
    pip:
      - yfinance
      - numpy
      - pandas
      - openpyxl
      - xgboost
      - scikit-learn
      - akshare
      - baostock
  system_requirements:
    - Python 3.10+
    - Network access to qt.gtimg.cn (Tencent), push2.eastmoney.com (Eastmoney), yahoo finance
---

# A股全市场缠论多维度分析系统

## 核心工作流

```
宏观因子 (期货持仓/美元/美债/商品)  ← 先看大环境
  └─ 个股分析
      ├── 缠论结构 (BSP/中枢/笔)
      ├── XGBoost 58维打分 (AUC 0.662)
      ├── 知识库确认 (规则+chanstock语义搜索)
      ├── SMC聪明钱 (Order Block/流动性/溢价区)
      ├── 量价分析 (放量/缩量/背离)
      └── 板块热度 (990个板块实时数据)
```

## 使用

```bash
cd scripts

# 单股分析
python3 analyze.py 002475     # A股
python3 analyze.py hk00700    # 港股

# 全市场扫描
python3 analyze.py --scan                    # A股全量
python3 analyze.py --scan --market hk        # 港股全量
python3 analyze.py --scan --min-score 70     # 仅高评分

# 模型训练
python3 train.py --stocks 27 --years 3
```

## 模块

| 模块 | 功能 |
|---|---|
| `analyze.py` | 主入口 —— 单股 + 全市场扫描 |
| `data.py` | 多源数据层 (Tencent/yfinance/AKShare/baostock 自动回退) |
| `chan_engine.py` | chan.py BSP/中枢提取 |
| `scorer.py` | 58维特征提取 + XGBoost打分 |
| `sector_heat.py` | 板块热度 (AKShare直连优先 → CSV → 腾讯推断) |
| `macro.py` | 宏观因子 (美债/DXY/汇率) |
| `futures_analysis.py` | COMEX商品期货分析 |
| `futures_sentiment.py` | CFFEX股指期货持仓 |
| `chan_kb.py` | 知识库确认 (chanstock语义搜索) |
| `smc_insight.py` | SMC聪明钱视角 |
| `volume_sector.py` | 量价分析 + 板块映射 |
| `train.py` | XGBoost训练器 |

## 数据源

| 源 | 行情 | K线 | 板块 | 重试 |
|---|---|---|---|---|
| 腾讯 qt.gtimg.cn | ✅ | ✅ | ✅(个股推断) | — |
| **AKShare (东财)** | — | ✅ | ✅ **990个板块** | ⚡ **5s重试** |
| yfinance | — | ✅ | — | — |
| baostock | — | ✅ | — | — |

### AKShare 重试机制

东财API有频率限制，请求超时需重试：

```python
for i in range(3):
    try:
        df = ak.stock_board_industry_name_em()
        break
    except:
        if i < 2: time.sleep(5 * (i + 1))
```

## 评分模型

58维特征 (BSP×12 + 价格×6 + MACD×5 + 布林×2 + 波动×3 + RSI×2 + ADX×2 + 量价×2 + 缠论结构×17 + 均线×5 + 量比×2)。训练用核心27只×3年滑动窗口。

## Pitfalls

### 数据源

- AKShare东财API有频率限制，请求超时需加重试（5/10/15s递增），不是IP被封
- 板块资金流腾讯接口 `zllr/zllc` 单位为元，需/10000转万元
- 港股K线用yfinance `%04d.HK` 格式，腾讯K线用 curl -sL（需跟踪重定向）
- baostock返回datetime.date对象，需 `str()` 转字符串
- 全量扫描时K线限制250根，避免chan.py分析过慢

### chan.py API兼容

- Bi对象使用 `bi.begin_klc.low` 和 `bi.end_klc.high` (不是 `.klc.low`)
- Seg对象使用 `seg.bi_list[-1].is_up` (不是 `seg.is_up` 或 `seg.end_klc.close`)
- yfinance单股下载返回MultiIndex列，需 `np.array(df['Close']).ravel()` 展平

### 缠论理论陷阱 ⚠️

**"上涨趋势确定后，不可能再有第一类与第二类买点，只可能有第三类买点"** — 缠中说禅 lesson 21

chan.py 的 BSP 检测是机械化的——它可能把强趋势中的回调标注为"二买"，但这在经典缠论中是不成立的：
- 年涨幅 > 100% 的股票 → 上升趋势已确立 → 不应出现一买/二买
- 这类"假二买"实际可能是：追高风险 or 三买的变体
- 处理：年涨幅 > 100% 的 Buy 信号需标注"⚠️ 趋势中二买存疑"，建议等三买确认

### 评分模型

- 无训练模型时 `predict_score` 自动回退到规则评分 `score_from_features`
- 训练使用 `models/chan_xgb_56d.pkl`，需与 `extract_features` 特征顺序一致

## 外部知识库

- [fpyluck/chanstock-skill](https://github.com/fpyluck/chanstock-skill) — 缠论知识库 + 语义搜索
- [MobiusQuant/OpenMobius-skill](https://github.com/MobiusQuant/OpenMobius-skill) — SMC/ICT概念库
- [bambuo/chan-model-xgb](https://github.com/bambuo/chan-model-xgb) — XGBoost特征框架
- [Vespa314/chan.py](https://github.com/Vespa314/chan.py) — 缠论引擎
