---
name: a-share-market-analysis
description: A股4454+港股780缠论全量分析：chan.py买卖点 → XGBoost 58维打分 → 量价/板块/宏观/SMC/知识库多维度共振。支持单股分析/全市场扫描。
version: 3.3.0
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

## 核心原则

1. **禁止胡编** — 所有数据必须标注来源字段（chan.py BSP/腾讯行情/yfinance/akshare）。不做工具未给出的推测性场景。如需解读，明确标注"以下为个人解读"。
2. **板块涨≠个股可买** — 热门板块涨停股往往是卖点。必须用阿娇标准二次确认。
3. **操作计划必须具体** — 买入区/止损/TP1/TP2/R:R，不能只说"买入"不给价格。

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
| `sync_sector_windows.py` | Windows端AKShare板块数据同步脚本 |
| `chanlun_kb_build.py` | chanstock知识库索引构建 |
| `chanlun_kb_search.py` | chanstock语义搜索CLI |

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

## 投资主线排序公式

选股不是只看安全边际——用户强调"要符合操作的主线，而不是仅仅看安全边际"。综合排序权重：

```
综合 = R:R盈亏比×40% + 评分×30% + 距买入区×20% + 板块热度×10%
```

- R:R = (TP1−买入) / (买入−止损)，上限10归一化
- 距买入区 = 负值越接近0越好（−4% > −11%，但R:R权重压倒距离）
- **不要仅凭"距现价最近"推荐** — 低R:R的股票靠近买入区也没有操作价值
- 板块热度来自 AKShare `stock_board_industry_name_em()` 实时涨跌排名推断
- 综合分≥55 = 第一梯队（进攻主力），50-54 = 第二梯队（弹性配置），<50 = 防守底仓

沪深300历史扫描结果参考 `references/chan_hs300_scan.csv`（333只→138买点→10中枢内）。

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
- **XGBoost维度匹配** — `predict_score` 必须用 `model.n_features_in_==feat_len` 检查，不能硬编码 `len(feats)==30`。模型是58维但规则特征也是58维，硬编码30会导致模型永远不被调用
- `model.n_features_in_` 是 sklearn API 的标准属性，在 `fit()` 后自动设置，无需手动维护
- 训练使用 `models/chan_xgb_56d.pkl`，需与 `extract_features` 特征顺序一致
- `extract_features` 返回 dict，训练时需 `[fd[k] for k in sorted(fd.keys())]` 转向量
- 58维特征中 chan.py 结构特征（bi/zs/seg）部分为0（chan.py对象属性不完全兼容），不影响整体AUC

### 30分钟多级别确认

`analyze_single()` 自动拉取30分钟K线做次级别确认：
- yfinance A股30m用 `period='5d', interval='30m'`（不是30d，A股30d 30m数据不可用）
- 港股30m同样用 `period='5d'`
- chan_engine.py 的日期解析必须兼容 `"2026-06-24"` 和 `"2026-06-24 09:30"` 两种格式（30m K线含时间）
- 确认逻辑：日线Buy + 30m Buy = ✅高确信 | 日线Buy + 30m非Buy = 🟡等次级别

### 全市场扫描综合评分

`scan_market()` 输出综合评分 = XGB×60% + 量价×20% + 板块×20%，并含阿娇过滤（年涨>100%非三买降15分）。Excel输出14列含量价/板块/阿娇警告。

### AKShare超时保护

`get_sector_from_akshare()` 在 `analyze_single()` 中必须限制重试次数（行业`max_retries=2`，概念`max_retries=1`），否则会阻塞单股分析60秒以上。全市场扫描时可放宽到3次。

## 板块扫描工作流

用户经常要求"分析热点板块的买入机会"。正确流程：

1. `ak.stock_board_industry_name_em()` 获取990个板块涨跌排名（含重试）
2. 取涨幅Top N板块，`ak.stock_board_industry_cons_em(symbol=板块名)` 获取成分股
3. 对每只成分股跑 chan.py + XGBoost + 阿娇筛选
4. **阿娇筛选是关键** — 板块暴涨≠个股可买。涨停股往往是"中枢上无信号"或"卖出信号"
5. 只输出：有中枢 + 中枢内/中枢上 + BSP买点 的标的

常见结果：热门板块（如锂+7.6%）阿娇筛选后0个买点——因为涨停股已涨完，剩余全部Hold/Sell。

## 外部知识库

- [fpyluck/chanstock-skill](https://github.com/fpyluck/chanstock-skill) — 缠论知识库 + 语义搜索
- [MobiusQuant/OpenMobius-skill](https://github.com/MobiusQuant/OpenMobius-skill) — SMC/ICT概念库
- [bambuo/chan-model-xgb](https://github.com/bambuo/chan-model-xgb) — XGBoost特征框架
- [Vespa314/chan.py](https://github.com/Vespa314/chan.py) — 缠论引擎
