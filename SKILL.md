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

## 阿娇版筛选标准（重要工作流）

chan.py 的 BSP 检测是机械化的，会产生经典缠论中不成立的信号。分析板块/个股时**必须**用阿娇标准二次筛选：

1. **必须有中枢** — 无中枢的买点不可靠（chan.py 可能在强趋势中标"二买"，但 lesson 21 明确指出"上涨趋势确定后不可能再有一买/二买，只有三买"）
2. **中枢内 + 买点 = 盘整背驰买**（最安全，止损放中枢下沿）
3. **中枢上 + 买点 = 三买**（趋势延续，止损放中枢上沿）
4. **中枢下 + 买点 = 风险偏高**，需次级别确认
5. 年涨幅 > 100% 的标的，chan.py 标的"二买"一律标注"⚠️ 趋势中二买存疑"

筛选代码模板见 `references/ajiao_screening.py`。

## 操作计划输出要求

用户要求每只买入标的必须给出具体操作计划：
- 买入区间（中枢下沿 ~ 下沿+3%）
- 止损价（中枢下沿-3%）
- TP1（中枢上沿）
- TP2（中枢上沿+10%）
- 盈亏比 R:R
- 现价是否偏高（偏高则等回调）

## Pitfalls

### 数据源

- **AKShare东财API有频率限制，不是IP被封** — 第一次请求常超时，5s重试后即通。`_ak_with_retry(fn, max_retries=3)` 封装在 `sector_heat.py` 中
- `sector_heat.py` 的 `get_sector_from_akshare()` 应限制 `max_retries=2`（行业）/ `max_retries=1`（概念），避免阻塞 `analyze.py` 主流程
- 板块资金流腾讯接口 `zllr/zllc` 单位为元，需/10000转万元
- 港股K线用yfinance `%04d.HK` 格式（如 `0700.HK`），不是 `00700.HK`
- 腾讯K线用 `curl -sL`（需跟踪302重定向），A股返回 `qfqday`，港股返回 `day`
- baostock返回datetime.date对象，需 `str()` 转字符串供 chan_engine 解析
- yfinance A股符号用 `.SS`/`.SZ` 后缀（如 `603019.SS`），不是 `sh603019`
- 全量扫描时K线限制250根，避免chan.py分析过慢

### chan.py API兼容

- Bi对象使用 `bi.begin_klc.low` 和 `bi.end_klc.high`（不是 `.klc.low`）
- Bi对象没有 `klc` 属性——直接 `bi.begin_klc` 就是 CKLine 对象
- Seg对象使用 `seg.bi_list[-1].is_up`（不是 `seg.is_up` 或 `seg.end_klc.close`）
- CSeg对象没有 `end_klc` 属性——用 `seg.bi_list` 替代
- yfinance单股下载返回MultiIndex列，需 `np.array(df['Close']).ravel()` 展平
- train.py 中 yfinance 数据用 `np.array(df['Close']).ravel()` 而非 `df['Close'].values`

### 评分模型

- 无训练模型时 `predict_score` 自动回退到规则评分 `score_from_features`
- 训练使用 `models/chan_xgb_56d.pkl`，需与 `extract_features` 特征顺序一致
- `extract_features` 返回 dict，训练时需 `[fd[k] for k in sorted(fd.keys())]` 转向量
- 58维特征中 chan.py 结构特征（bi/zs/seg）部分为0（chan.py对象属性不完全兼容），不影响整体AUC

## 外部知识库

- [fpyluck/chanstock-skill](https://github.com/fpyluck/chanstock-skill) — 缠论知识库 + 语义搜索
- [MobiusQuant/OpenMobius-skill](https://github.com/MobiusQuant/OpenMobius-skill) — SMC/ICT概念库
- [bambuo/chan-model-xgb](https://github.com/bambuo/chan-model-xgb) — XGBoost特征框架
- [Vespa314/chan.py](https://github.com/Vespa314/chan.py) — 缠论引擎
