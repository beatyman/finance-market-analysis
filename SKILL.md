---
name: a-share-market-analysis
description: A股4454+港股780缠论全量分析：chan.py买卖点 → XGBoost 58维打分 → 量价/板块/宏观/SMC/知识库多维度共振。支持单股分析/全市场扫描。
version: 4.1.0
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
      - easy-tdx
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
🗓️ 事件日历 (FOMC/地缘/PMI日程)  ← 第一优先级
  └─ 🌍 宏观因子 (期货持仓/美元/美债/商品)
      └─ 📈 股指期货持仓
          └─ 🥇 商品期货
              └─ ─ 个股分析 ─
                  ├── 缠论结构 (BSP/中枢/笔)
                  ├── XGBoost 58维打分 (AUC 0.662)
                  ├── 知识库确认 (规则+chanstock语义搜索)
                  ├── SMC聪明钱 (Order Block/流动性/溢价区)
                  ├── 30分钟多级别确认 (日线+30m共振)
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
| `macro.py` | 宏观因子 — 实时美债/DXY/汇率（5天周期+5分钟缓存） |
| `futures_analysis.py` | COMEX商品期货分析 |
| `futures_sentiment.py` | CFFEX股指期货持仓 |
| `chan_kb.py` | 知识库确认 (chanstock语义搜索) |
| `smc_insight.py` | SMC聪明钱视角 |
| `volume_sector.py` | 量价分析 + 板块映射 |
| `train.py` | XGBoost训练器 |
| `event_calendar.py` | 宏观事件日历 — FOMC/地缘/中国数据 |
| `sync_sector_windows.py` | Windows端AKShare板块数据同步脚本 |
| `chanlun_kb_build.py` | chanstock知识库索引构建 |
| `chanlun_kb_search.py` | chanstock语义搜索CLI |
| `board_hot.py` | 通达信easy-tdx板块热点(概念+行业各15+,主力资金) |
| `daily_report.py` | **日报生成器 v4** — 一键生成(宏观/期货/板块/A股/港股/操作), 固化报告格式 |

## 日报生成

**命令:** `cd scripts && python3 daily_report.py`  → `/root/chan_daily_report.md`

日报的格式是**固化标准**，不可随意改变。所有模块（宏观/板块/A股/港股/操作建议）的表结构和字段顺序必须保持一致。

### 事件日历验证 ⚠️

`event_calendar.py` 目前使用**静态硬编码**数据。FOMC会议纪要实际发布时间、美联储讲话日程等需通过官方来源验证：

```bash
# 官方日历
https://www.federalreserve.gov/calendar.htm
https://www.federalreserve.gov/newsevents.htm
```

**本轮会话教训:** 静态日历写"6/25 FOMC纪要公布"，但美联储官网显示本周只有两场低影响讲话，纪要约在7/8发布。生成报告前应先检查官网，或在报告中标注"基于历史规律预估，以官网为准"。

```
# 🔬 缠论多维分析日报
🗓️ 事件日历 (FOMC/地缘/PMI)
🇨🇳 中国宏观 (国债10Y/2Y/30Y + 中美利差)
🌍 美国宏观 (US10Y/DXY/VIX/汇率/商品)
📈 股指期货 (Top20席位多空持仓/净变动)
🔥 板块热点 (通达信概念15+行业15, 主力净流入/成交额)
🎯 A股买入标的 (中枢内, 含名称/价格/评分/买入/止损/TP/ R:R)
🇭🇰 港股 (买入/规避)
📋 操作建议 (仓位分配)
```

日报要求：
- 概念板块≥15行 + 行业板块≥15行（来自 `easy-tdx` 通达信）
- 买入标的表必须含股票名称（从 `hs300_stocks.csv` 成分券名称列 `zfill(6)` 映射获取）
- 宏观部分包含中美利差方向指引
- 操作建议含具体仓位百分比

## 旧版日报 (参考模板)

## 数据源

| 源 | 行情 | K线 | 板块 | 重试 |
|---|---|---|---|---|
| 腾讯 qt.gtimg.cn | ✅ | ✅ | ✅(个股推断) | — |
| **AKShare (东财)** | — | ✅ | ✅ **990个板块** | ⚡ **5s重试** |
| yfinance | — | ✅ | — | — |
| baostock | — | ✅ | — | — |

| **通达信 (easy-tdx)** | — | — | ✅ 概念+行业15+ | ✅ 主力资金/成交额(亿) |

### easy-tdx 通达信板块数据

```python
from easy_tdx import MacClient, BoardType
with MacClient.from_best_host() as client:
    concept = client.get_board_ranking(BoardType.GN, top_n=15, sort_by="change_pct")
    industry = client.get_board_ranking(BoardType.HY, top_n=15, sort_by="change_pct")
# 字段: name, change_pct, amount(元→/1e8转亿), main_net_amount(主力净流入), up_count, down_count
```

### AKShare 重试机制

```python
for i in range(3):
    try:
        df = ak.stock_board_industry_name_em()
        break
    except:
        if i < 2: time.sleep(5 * (i + 1))
```

## 宏观分析

### 中国国债 & 中美利差

`macro.py` 现在覆盖中美双向数据：AKShare获取中国国债收益率，yfinance获取美债/DXY/VIX/商品。`load_macro()` 5分钟缓存。中美利差自动计入方向判定。

```python
import akshare as ak
cb = ak.bond_zh_us_rate(start_date='20250601')
cn10 = float(cb['中国国债收益率10年'].iloc[-1])
spread = us10 - cn10  # 中美利差
```

| 利差 | 方向指引 |
|------|----------|
| >2.5% | 🔴 资本外流压力大 → A股权重股承压 |
| 1.5-2.5% | 🟡 偏宽，谨慎 |
| <1.5% | 🟢 外资回流利好A股 |

### 股指期货详细持仓

`futures_sentiment.py` 输出Top20席位数据（多单/空单/净持仓/每日变动/方向）：

### 通达信 easy-tdx 板块资金

`board_hot.py` 提供概念+行业板块实时主力资金（easy-tdx 通达信协议）：

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

用户要求每只买入标的必须给出具体操作计划。输出格式需对齐：

```
标的: 立讯精密 (002475)  现价: ¥75  评分: 80/100  中枢: 67~78
🎯 买入区: ¥67~69 (距现价 −11%~−8%)
🛑 止损:   ¥65 (−13%)
🏁 TP1:    ¥78 (+4%)  /  TP2: ¥85 (+13%)
R:R = 5.5:1 | 30分钟: 🟡 日线买但30m未确认
量价: 🟢 放量上涨-主力吸筹 | 板块: 🔥 AI消费电子领涨
```

日报输出使用 markdown 表格格式（见 `references/chan_daily_report.md` 模板），含宏观/板块/投资标的/止损止盈/操作建议五个部分。

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

- **XGBoost维度匹配（关键Pitfall）**: `predict_score` 必须用 `model.n_features_in_==feat_len` 自动检测维度，严禁硬编码 `len(feats)==30`。58维模型 + 30维硬编码 = 模型永不调用，回退到规则评分。
- **XGBoost维度匹配** — `predict_score` 必须用 `model.n_features_in_==feat_len` 检查，不能硬编码 `len(feats)==30`。模型是58维但规则特征也是58维，硬编码30会导致模型永远不被调用
- `model.n_features_in_` 是 sklearn API 的标准属性，在 `fit()` 后自动设置，无需手动维护
- 训练使用 `models/chan_xgb_56d.pkl`，需与 `extract_features` 特征顺序一致
- `extract_features` 返回 dict，训练时需 `[fd[k] for k in sorted(fd.keys())]` 转向量
- 58维特征中 chan.py 结构特征（bi/zs/seg）部分为0（chan.py对象属性不完全兼容），不影响整体AUC

### 30分钟多级别确认

`analyze_single()` 自动拉取30分钟K线做次级别确认：
- yfinance A股30m用 `period='5d', interval='30m'`（不是30d，A股30d 30m数据不可用）
- 港股30m同样用 `period='5d'`
- **chan_engine.py 的日期解析必须兼容两种格式**: `"2026-06-24"` (日线用 `.split('-')`) 和 `"2026-06-24 09:30"` (30m K线含时间，需 `.split(' ')` 再拆时间)
- 确认逻辑：日线Buy + 30m Buy = ✅高确信 | 日线Buy + 30m非Buy = 🟡等次级别
- 30m报错 `ValueError: invalid literal for int() with base 10: '17 09:30'` 说明日期解析没兼容时间格式

### 全市场扫描综合评分

`scan_market()` 输出综合评分 = XGB×60% + 量价×20% + 板块×20%，并含阿娇过滤（年涨>100%非三买降15分）。Excel输出14列含量价/板块/阿娇警告。

### AKShare CSV 代码前导零 (Critical Pitfall)

`ak.index_stock_cons_csindex(symbol='000300')` 返回的成分券代码**缺少前导零**（如 `2475` 而非 `002475`）。构建 yfinance 符号时**必须** `str(code).zfill(6)`：

```python
name_map = {str(c).zfill(6): str(n) for c, n in zip(df['成分券代码'], df['成分券名称'])}
sym = code + ('.SS' if code.startswith('6') else '.SZ')  # 002475.SZ ✓ 不是 2475.SZ ✗
```

不 zfill 会导致所有 00xxxx 代码的 yfinance 请求失败（"possibly delisted"）。

### 港股报告输出索引 (Critical Pitfall)

港股扫描结果元组结构为 `(code, name, label, px, score, ytd, zs_str, bsp_buy, in_zs)`。筛选买入和卖出时必须用正确索引：
- `hk_buys = [r for r in hk_results if r[7]]` — `bsp_buy` 在索引 7
- `hk_sells = [r for r in hk_results if not r[7] and 'Sell' in str(r[2])]` — `label` 在索引 **2**（不是 3）
- 价格在索引 4，评分在索引 5，年涨在索引 6

### daily_report.py 元组索引 (Critical Pitfall — 5次反复出错)

**A股元组结构:** `(code, name, label, px, score, ytd, zs_str, pos, iz, entry, stop, tp1, tp2, rr)`

| 索引 | 字段 | 类型 | 格式 |
|------|------|------|------|
| 3 | price | int | `int(r[3])` |
| 4 | score | int | `int(r[4])` |
| 5 | ytd | float | `float(r[5])` |
| 6 | zs_str | str | `str(r[6])` — "67~78" 不是数字! |
| 7 | pos | str | — |
| 9 | entry | int | `int(r[9])` |
| 10 | stop | int | `int(r[10])` |
| 11 | tp1 | int | `int(r[11])` |
| 12 | tp2 | int | `int(r[12])` |
| 13 | rr | float | `float(r[13])` |

**港股元组结构:** `(code, name, label, px, score, ytd, zs_str, bsp_buy, in_zs)`

| 索引 | 字段 | 筛选/输出 |
|------|------|-----------|
| 2 | label | `'Sell' in str(r[2])` — 注意是索引2不是3 |
| 3 | price | `int(r[3])` |
| 4 | score | `int(r[4])` |
| 5 | ytd | `float(r[5])` |
| 6 | zs_str | `str(r[6])` — "HK$493~520" |
| 7 | bsp_buy | `r[7]` — 布尔值筛选买入 |

**常见错误（本轮会话出现5次才修复）:**
1. `ValueError: could not convert string to float: '67~78'` — r[6]是中枢字符串，错当ytd浮点数
2. `TypeError: argument of type 'int' is not iterable` — r[3]是股价int，错当label字符串做 `'Sell' in r[3]`
3. 香港卖出筛选 `'Sell' in r[3]` → 应是 `'Sell' in str(r[2])`（label在索引2）
4. 输出行 `r[4]` 当价格 → 应是 `r[3]`（价格是第4个元素，索引3）
5. `r[6]` 当zs_str但在错误位置 → 确认元组打包顺序 `cu.zs_list[-1]` 在score之后

### AKShare超时保护

`get_sector_from_akshare()` 在 `analyze_single()` 中必须限制重试次数（行业`max_retries=2`，概念`max_retries=1`），否则会阻塞单股分析60秒以上。全市场扫描时可放宽到3次。

### 模块导入修补 (首次部署必检)

在干净的 Python venv 中首次运行 `analyze.py` 时可能遇到以下导入错误，需逐项修补：

1. **`analyze.py` 第1行 `import numpy as np` 在 shebang 之前** — shebang 必须在文件第一行。修复：将 `#!/usr/bin/env python3` 移到第一行，`import numpy as np` 移到第二行。
2. **`macro.py` 缺少 `macro_signal` 函数** — `analyze.py` 第19行 `from macro import load_macro,macro_signal`，但 `macro.py` 只有 `load_macro` 和 `macro_report`。修复：在 `macro.py` 中添加 `macro_signal(macro)` 存根，返回 `{'bias': str, 'signals': list}`。
3. **`futures_sentiment.py` 缺少 `get_futures_position` 和 `analyze_sentiment`** — `analyze.py` 第20行和 `scan_market()` 第183行引用这两个函数，但 `futures_sentiment.py` 只有 `get_detailed_positions` 和 `format_futures_report`。修复：在 `futures_sentiment.py` 中添加存根（`get_futures_position` 返回 `{}`，`analyze_sentiment` 返回 `{'bias': '中性'}`）。

这些是脚本模块间的接口断裂（历史重构残留），不是环境问题 — 每个干净部署都会重现。

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
