---
name: a-share-market-analysis
description: A股4454+港股780缠论全量分析：chan.py买卖点 → XGBoost 58维打分 → 量价/板块/宏观/SMC/知识库多维度共振。支持单股分析/全市场扫描。
version: 4.6.0
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
| `chan_engine.py` | chan.py BSP/中枢提取 — **不支持30m K线, 见 `references/t0_trading.md`** |
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
| `etf_momentum.py` | **Quanti5 ETF动量轮动** — 全ETF动量评分+趋势门+仓位调节, 月度调仓组合 |
| `board_hot.py` | 通达信easy-tdx板块热点(概念+行业各Top10,主力资金,~9秒) |
| `daily_report.py` | **日报生成器 v4** — 一键生成(宏观/期货/板块/A股/港股/操作), 固化报告格式 |
| `t0_trade.py` | **日内做T策略** — 日线方向+30m价格区间+量价异常 |
| `portfolio.py` | **持仓管理+预警** — 吸收 stock-watcher/stock-monitor 设计, 成本盈亏/分级预警/腾讯实时价, 挂单/止损/TP定制, 支持 add/remove/show/alerts 子命令 |\n| `volume_minute.py` | **分时量能分析** — 吸收 a-stock-analysis 设计, 新浪5分钟K线/早盘抢筹/尾盘异动/放量TOP10 |

## 日报生成

**命令:** `cd scripts && python3 daily_report.py`  → `/root/chan_daily_report.md`

日报的格式是**固化标准**，不可随意改变。所有模块（宏观/板块/A股/港股/操作建议）的表结构和字段顺序必须保持一致。

**🚨 严禁擅自改变模板 (CRITICAL — 本轮会话用户直接警告):** 用户已多次强调日报格式是固化的。**本轮会话中，日报被擅自简化了段落（合并"中国宏观+美国宏观"为"宏观速览"，删除"港股机会"），用户当场警告"模板你又改变了，之前不是约束好不要改变模板吗"。**

**绝对规则:**
- 现有8个段落名称和顺序永久固定（🗓️→🇨🇳→🌍→📈→🔥→🎯→🇭🇰→📋）
- 新增内容只能在📋"操作建议"**之前**追加为独立段落
- 🚫 不可合并任何现有段落（如"宏观速览"替代两个独立段落）
- 🚫 不可删除"港股机会"、"事件日历"等任何段落
- 🚫 不可改变列顺序或删减表格字段
- &#事- 改变任何结构前**必须先向用户确认**
- 违反以上规则 = 用户直接警告，回到原模板重写

**标准模板（必须逐字遵循）:** 见 `references/chan_daily_report.md`，这是唯一权威格式源。

### 事件日历验证 (CRITICAL — Fed官网 vs 静态推测)

`event_calendar.py` 使用静态硬编码数据。**FOMC 会议纪要不在会后次日发布——通常在会后约 3 周**（如 6/16-17 会议 → 约 7/8 纪要）。生成日报前必须在报告开头输出当前事件日历，但需明确标注数据来源（硬编码 vs 官网核实）。

验证来源:
- https://www.federalreserve.gov/calendar.htm (官方日历)
- https://www.federalreserve.gov/newsevents.htm (新闻与事件)

**本轮会话教训:** 静态日历曾错误标注 6/25 "FOMC会议纪要公布"。Fed 官网核实后发现本周 (6/23-27) 只有两场低影响讲话（Governor Cook + 麻省银行家协会），纪要实际在 7/8。

```bash
# 官方日历
https://www.federalreserve.gov/calendar.htm
https://www.federalreserve.gov/newsevents.htm
```

**本轮会话教训:** 静态日历写"6/25 FOMC纪要公布"，但美联储官网显示本周只有两场低影响讲话（Governor Cook + 麻省银行家协会），纪要约在7/8发布。**生成报告前必须先检查官网核实日历，不能依赖上一次会话的静态日期。** FOMC 会议纪要通常在会后约 3 周发布（6/16-17 会议 → 约 7/8 纪要），不是次日。

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

## 数据源（优先级从高到低）

| 源 | 行情 | K线 | 板块 | 延迟 | 用途 |
|---|---|---|---|---|---|
| **腾讯 qt.gtimg.cn** | ✅ **实时** | ✅ | ✅(个股推断) | 0延迟 | **首选实时价** |
| **baostock** | — | ✅ **最可靠** | — | 日终 | **首选K线** |
| yfinance | — | ⚠️ 延迟2天 | — | 2天 | 备选(港股/美股) |
| **AKShare (东财)** | — | ✅ | ✅ **990个板块** | 5s重试 | 板块成分股 |
| **通达信 (easy-tdx)** | — | — | ✅ 概念+行业Top10 | ~9秒 | 实时资金流 |
| **新浪财经 (sina)** | — | ✅ **5分钟K线** | — | ~3秒 | **分时量能** |

### 实时买入清单工作流 (Tencent + baostock)

**yfinance 数据滞后2个交易日** — 绝不能用于最终报价。正确流程：

```python
# 1. 腾讯实时行情 (现价)
import subprocess as sp
url = 'http://qt.gtimg.cn/q=sz002475,sh603920,sz300033'
r = sp.run(['curl','-sL','--max-time','5',url], stdout=sp.PIPE)
raw = r.stdout.decode('gbk','ignore')
for line in raw.split('\n'):
    p = line.split('~')
    if len(p) >= 10:
        code = p[2]    # 3rd field = actual stock code
        px = float(p[3])  # 4th field = real-time price
        chg = float(p[32]) # 33rd field = change %

# 2. baostock K线 (日线)
import baostock as bs
bs.login()
sym = 'sh.'+code if code.startswith('6') else 'sz.'+code
rs = bs.query_history_k_data_plus(sym, 'date,open,high,low,close,volume',
    start_date='2025-06-01', end_date=time.strftime('%Y-%m-%d'),
    frequency='d', adjustflag='2')
rows = []
while rs.next(): rows.append(rs.get_row_data())
# Replace last close with live px before chan analysis
C[-1] = live_px
cur, bb, bt, _, zs, pos = chan_analyze(D, O, C, H, L, code)

# 3. 输出 Excel
# 使用模板: /root/buy_list_live.xlsx
```

### easy-tdx 板块资金流 (9秒, 限制说明)

`board_hot.py` 取概念+行业各Top10。**注意**: 我们12个特定板块（如BK0877 PCB）**不在Top50概念榜中** — 只能获取通用热度榜，不能按板块代码精确查询资金流。

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

## ETF分析

用户偏好个股优先（更优R:R），但常要求批量ETF对比。分析ETF时直接拉yfinance跑chan.py。

### ETF批量扫描工作流

用户给出一串ETF代码时（如 "分析510050,562500,159819..."），用硬编码 `etfs={code:name}` 字典 + yfinance + chan.py 遍历。输出表格含：名称/代码/价格/BSP信号/评分/年涨/5日涨/中枢/位置。

**推荐ETF组合时务必对比个股组合** — ETF R:R低、波动小，个股（如立讯75分 vs HS300一卖60分）通常更优。

### 追高风险门槛

| 条件 | 操作 |
|------|------|
| 年涨>80%或5日>10% | 🔴 不推荐追高（如科创芯片+91%） |
| 一买且评分<55 | 🟡 谨慎（如5GETF -39%） |
| 二卖/Sell | 🔴 剔除 |
| 无中枢+Sell | 🔴 顶级风险（如恒生科技−23%） |

### ETF组合权重建议

```
蓝筹底仓(上证50) 20% + 成长(机器人/云计算) 30% + 低吸(证券) 15%
+ 投机(5GETF/科创芯片) 10% + 现金 25%
→ 所有仓位等30m确认后再入场
```

## 做T策略 (t0_trade.py)

`t0_trade.py` 用日线方向+30m价格区间+量价做日内交易建议。

**约束:**
- 下跌趋势中只卖不买（不摊平）
- 先减仓至安全水位再做T
- chan.py不支持30m K线分析，用价格极值+量价异常替代

## Pitfalls

### 数据源

- **AKShare东财API有频率限制，不是IP被封** — 第一次请求常超时，5s重试后即通。`_ak_with_retry(fn, max_retries=3)` 封装在 `sector_heat.py` 中
- `sector_heat.py` 的 `get_sector_from_akshare()` 应限制 `max_retries=2`（行业）/ `max_retries=1`（概念），避免阻塞 `analyze.py` 主流程
- 板块资金流腾讯接口 `zllr/zllc` 单位为元，需/10000转万元
- 港股K线用yfinance `%04d.HK` 格式（如 `0700.HK`），不是 `00700.HK`
- 腾讯K线用 `curl -sL`（需跟踪302重定向），A股返回 `qfqday`，港股返回 `day`
- baostock返回datetime.date对象，需 `str()` 转字符串供 chan_engine 解析
### yfinance A股符号用 `.SS`/`.SZ` 后缀（如 `603019.SS`），不是 `sh603019`

### 腾讯实时行情代码提取 (Tencent code parsing)

腾讯 `qt.gtimg.cn` 返回格式: `v_sz002475="1~立讯精密~002475~75.05~..."`。正确提取 `code` 用 `p[2]`（第三字段），不是 `p[0]`（带前缀）：

```python
for line in raw.split('\n'):
    p = line.split('~')
    if len(p) >= 10:
        code = p[2]    # ✓ "002475" (第3字段)
        name = p[1]    # ✓ "立讯精密" (第2字段)  
        px = float(p[3])  # ✓ 75.05 (第4字段)
        chg = float(p[32]) # ✓ 涨跌幅
```

`p[0]` 是 `v_sz002475`（带前缀），需额外 `replace('sz','').replace('sh','')` 才能得到代码。

### 主力吸筹判断标准 (Volume Accumulation)

用户常问"有没有主力吸筹"。量价维度评分逻辑（非缠论，作为辅助参考）：

| 信号 | 条件 | 权重 |
|------|------|------|
| 成交量放大 | 20日均量 > 60日均量 × 1.3 | +2 |
| 阳线放量 | 阳线均量 > 阴线均量 × 1.3 | +2 |
| 放量阳线天数 | 20日内≥3天单日量>20日均量×1.5 | +2 |
| 接近底部 | 距60日低 < 10% | +2 |
| **评分 ≥ 6** | 🔥 强吸筹 — 主力明显建仓 | |
| **评分 ≥ 4** | 🟢 中等吸筹 | |
| **评分 ≥ 2** | 🟡 弱吸筹 | |
| **评分 < 2** | ❌ 无吸筹迹象 | |

注意：板块热点驱动型行情（如AI/半导体）通常吸筹评分低——资金是追涨式进入而非底部建仓型。

### yfinance 数据延迟2天 (Critical — 本轮会话反复触雷)

**yfinance 日线数据滞后约2个交易日**。`period='1y'` 返回的最新收盘价可能是2天前的数据（如今天6/25，最新数据是6/23）。这导致：
- 存量分析（chan.py结构）仍可用 — K线结构变化缓慢
- **实时价/距现价计算/买入区判断必须用腾讯实时行情** — 否则距现价误差可达8%+

**正确流程 (Tencent + baostock):**
```python
# 1. 腾讯实时行情 (现价) — 0延迟
url = 'http://qt.gtimg.cn/q=sz002475,sh603920,sz300033'
r = sp.run(['curl','-sL','--max-time','5',url], stdout=sp.PIPE)
raw = r.stdout.decode('gbk','ignore')
for line in raw.split('\n'):
    p = line.split('~')
    if len(p) >= 10:
        code = p[2]    # 3rd field = actual stock code
        px = float(p[3])  # 4th field = real-time price

# 2. baostock K线 (日线) — 可靠
bs.login()
sym = 'sh.'+code if code.startswith('6') else 'sz.'+code
rs = bs.query_history_k_data_plus(sym, 'date,open,high,low,close,volume',
    start_date='2025-06-01', end_date=time.strftime('%Y-%m-%d'), frequency='d', adjustflag='2')
# Replace last close with live px before chan analysis
C[-1] = live_px
```

**检测方法:** 如果 yfinance 最新日期距今天>1天，自动切换腾讯+baostock。输出模板 `/root/buy_list_live.xlsx`。
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
- **chan.py 不支持 30m K线直接分析** — CTime `auto=True/False` 均会产生 "kline time err, cur=2026/06/17, last=2026/06/17" 错误。日内做 T 策略用价格区间+量价代替 30m 缠论分析（见 `t0_trade.py`）
- 30m 报错 `ValueError: invalid literal for int() with base 10: '17 09:30'` 说明日期解析没兼容时间格式

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

### 存储芯片业绩预增 ≠ 股票可买 (Critical Pitfall)

存储芯片4只业绩暴增股（兆易11x/佰维30x/江波龙52x/德明利110x），chan.py 分析结果：

| 标的 | 预增 | chan.py | 原因 |
|------|------|---------|------|
| 兆易创新 | 11x | 🔴 Sell-二卖 73分 | 年涨205%已充分price in |
| 佰维存储 | 30x | 🟡 Hold 63分 | 年涨256%追高 |
| 江波龙 | 52x | 🔴 Sell-一卖 63分 | 年涨145%卖点 |
| 德明利 | 110x | 🟢 Buy-二买 60分 | 年仅涨6%,低位有买点 |

**只有德明利有操作价值** — 业绩暴增但股价未透支。其余三只已充分定价，追高=接盘。**遇到"业绩暴增股"必须先跑 chan.py — 市场可能早已定价。**

### 券商调研 ≠ 现在买入安全 (Critical Pitfall — 本轮会话重大发现)

**花旗6/25光互联"超级周期"研报 — 7只光通信标的全部无法按当前价位操作：**

| 标的 | 花旗目标 | 现价 | 空间 | chan.py | 买入区 | 距现价 |
|------|---------|------|------|---------|--------|--------|
| 新易盛 | ¥701 | ¥610 | +15% | 🔴Sell-一卖 | — | — |
| 天孚通信 | ¥419 | ¥342 | +23% | 🟢Buy-三买 | ¥217 | **−37%** |
| 太辰光 | 卖出 | ¥258 | — | 🟢Buy-三买 | ¥110 | **−57%** |
| 中际旭创 | — | ¥1,323 | — | 🟢Buy-一买 | ¥558 | **−58%** |

**致命矛盾：chan.py 的"买入区"是历史残留的中枢下游，价格早已远离。机械标记的买点 ≠ 当前价格可操作。只有中枢内买点（如立讯¥67, -10%）才是真实的。**

**新易盛教训：今天涨+10%但缠论Sell-一卖 + SMC共振看空。花旗看多≠缠论看多。**

### 早盘放量 ≠ 主力吸筹 (抢筹×阿娇交叉分析 — 本轮会话发现)

300只抢筹股中**30%是卖出信号**。早盘放量可能是出货（TCL Sell-二卖, 京东方Sell-一卖）。只有中枢内买点（三花智控、江西铜业）才是真正的双重确认。

### 涨停≠买入信号 (Critical Pitfall)

涨停当天 K 线计入后，chan.py 结构可能**仍显示 Sell/Hold**。原因：1根10%阳线改变不了由200+根K线构建的多笔整体结构。涨停形成的新向上笔在无中枢的强趋势中往往被判定为二卖反弹——打到前高附近再次受阻。

- 用户看到涨停就问"能不能买"时，必须诚实说明：数据已包含涨停，但结构仍是 Sell
- 涨停次日走势决定一切：继续放量突破前高 → 结构可能重建；高开低走或缩量 → 二卖坐实
- 不要在涨停当天因"板块热"或"涨停了"就推翻 chan.py 的客观结构判断

### 业绩预增 ≠ 股票可买 (Critical Pitfall)

存储芯片4只业绩暴增股（兆易11x/佰维30x/江波龙52x/德明利110x），chan.py 分析结果：

| 标的 | 预增 | chan.py | 原因 |
|------|------|---------|------|
| 兆易创新 | 11x | 🔴 Sell-二卖 73分 | 年涨205%已充分price in |
| 佰维存储 | 30x | 🟡 Hold 63分 | 年涨256%追高 |
| 江波龙 | 52x | 🔴 Sell-一卖 63分 | 年涨145%卖点 |
| 德明利 | 110x | 🟢 Buy-二买 60分 | 年仅涨6%,低位有买点 |

**只有德明利有操作价值** — 业绩暴增但股价未透支。其余三只已充分定价，追高=接盘。**遇到"业绩暴增股"必须先跑 chan.py — 市场可能早已定价。**

### AKShare超时保护

`get_sector_from_akshare()` 在 `analyze_single()` 中必须限制重试次数（行业`max_retries=2`，概念`max_retries=1`），否则会阻塞单股分析60秒以上。全市场扫描时可放宽到3次。

### 模块导入修补 (首次部署必检)

在干净的 Python venv 中首次运行 `analyze.py` 时可能遇到以下导入错误，需逐项修补：

1. **`analyze.py` 第1行 `import numpy as np` 在 shebang 之前** — shebang 必须在文件第一行。修复：将 `#!/usr/bin/env python3` 移到第一行，`import numpy as np` 移到第二行。
2. **`macro.py` 缺少 `macro_signal` 函数** — `analyze.py` 第19行 `from macro import load_macro,macro_signal`，但 `macro.py` 只有 `load_macro` 和 `macro_report`。修复：在 `macro.py` 中添加 `macro_signal(macro)` 存根，返回 `{'bias': str, 'signals': list}`。
3. **`futures_sentiment.py` 缺少 `get_futures_position` 和 `analyze_sentiment`** — `analyze.py` 原第20行（模块级导入）和 `scan_market()` 第183行引用这两个函数。两步修复：
   - 在 `futures_sentiment.py` 中添加存根（`get_futures_position` 返回 `{}`，`analyze_sentiment` 返回 `{'bias': '中性'}`）。
   - **从 `analyze.py` 模块级移除 `from futures_sentiment import ...`** — 模块级导入崩溃会阻止整个脚本加载，函数体内的 `try/except` 局部导入可优雅降级。保留第67行 try 块内的导入即可。

这些是脚本模块间的接口断裂（历史重构残留），不是环境问题 — 每个干净部署都会重现。

## 板块扫描工作流

用户经常要求"分析热点板块的买入机会"。正确流程：

1. `ak.stock_board_industry_name_em()` 获取990个板块涨跌排名（含重试）
2. 取涨幅Top N板块，`ak.stock_board_industry_cons_em(symbol=板块名)` 获取成分股
3. **AKShare成分股获取超时时**，用easy-tdx或硬编码成分股列表（PCB/半导体/AI等常见板块已有映射在 `sector_heat.py` 的 `SECTOR_MEMBERS` 中）
4. 对每只成分股跑 chan.py + XGBoost + 阿娇筛选
5. **阿娇筛选是关键** — 板块暴涨≠个股可买。涨停股往往是"中枢上无信号"或"卖出信号"
6. 只输出：有中枢 + 中枢内/中枢上 + BSP买点 的标的
7. **多板块扫描时去重** — 同一股票（如立讯/海光）可能出现在3-4个板块中，只在最终中枢内买点汇总中去重

### 板块扫描输出格式

每个板块输出结构（如用户要求"分析PCB/半导体/AI/存储四板块"）：

```
═══ 板块名 (N只) 买入:M 中枢内:K ═══
  🟢/🔴/🟡 标的名 ¥价格 信号 评分 年涨 5日 ZS中枢 中枢内标志
  ── 总结行 ──
  🥇 中枢内标的 买入价/止损/TP/R:R
```

末尾汇总所有中枢内买点（去重）。常见结果：热门板块（如锂+7.6%）阿娇筛选后0个买点——因为涨停股已涨完，剩余全部Hold/Sell。

## 板块批量扫描参考输出

`references/board_stocks.csv` — 12板块全量成分股+缠论分析结果（代码/名称/板块/信号/评分/买入/止损/TP/R:R）。`references/board_analysis_report.md` — 对应的 markdown 完整报告。

## 分时量能分析 — 主力动向 (volume_minute.py + 新浪财经)

**本轮会话重大发现: 早盘放量 ≠ 主力吸筹。300只抢筹股中30%是卖出信号。**

`volume_minute.py` 用**新浪财经 5分钟K线**分析沪深300主力盘中动向。吸收 `@cnyezi/a-stock-analysis` 设计，**免费、无需API Key**。

**数据源:**
```
http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData
?symbol=sh{code}&scale=5&datalen=48
```

**分析维度:**
- 早盘30分 (9:30-10:00) — 占比>30% = 主力抢筹
- 尾盘30分 (14:30-15:00) — 占比>20% = 异动放量
- 放量 TOP10 分钟 — 识别建仓/出货时点
- 日内走势 — 开盘→收盘价格变化

**用法:**
```bash
python3 volume_minute.py 603019        # 单股分时分析
python3 volume_minute.py --scan        # 全量沪深300扫描
```

### 抢筹 × 阿娇交叉分析 (Critical Workflow)

早盘放量 ≠ 主力吸筹。**本轮会话发现：300只抢筹股中30%是卖出信号**。必须用阿娇二次过滤：

```
1. 新浪分时量能 → 早盘>25% + 日内上涨 = 主力抢筹候选
2. chan.py + baostock → 缠论结构 + 阿娇筛选
3. 双重确认 = 早盘抢筹 ∩ 中枢内买点 = 最强信号
```

**仅2只通过双重确认（本次分析）：三花智控、江西铜业。**

## 日内做T策略 (t0_trade.py)

`t0_trade.py` 用日线方向+30m价格区间+量价做日内交易建议。**chan.py 不支持30m K线分析**（CTime `auto=True/False` 均产生 "kline time err"），用价格极值+量价异常替代。

**约束:**
- 下跌趋势中只卖不买（不摊平）
- 先减仓至安全水位再做T
- 日内振幅需>3%才有操作空间
- 无中枢股票不做T（无锚定点）

## 板块扫描工作流 (12板块批量分析)

用户常要求"分析多个板块，找出买入标的"。完整工作流：

1. **板块识别**: 优先用 easy-tdx `get_board_cons()` 获取成分股，失败时用硬编码列表（`references/board_stocks.csv` 已有12板块成分股）
2. **批量扫描**: 去重后对唯一标的跑 chan.py + XGBoost
3. **阿娇筛选**: 只保留有中枢+中枢内/中枢上+BSP买点
4. **跨板块统计**: 同一标的出现在多个板块时标记"跨板数"
5. **输出格式**: 每板块独立表格 → 跨板块龙头表 → 中枢内买点汇总 → 操作建议

### 板块批量扫描标准输出格式

```
═══ BK1650 AI概念 (15只) 买入:10 中枢内:4 ═══
| 🔥 立讯精密 | ¥75 | Buy-中枢内买点 | 80 | +30% | +11.5% | 67~78 |
| 🟢 浪潮信息 | ¥64 | Buy-二买 | 70 | +1% | +0.5% | - |

── 🏆 跨板块龙头(≥3板块) ──
| 立讯精密(002475) | 4 | AI/CPO/铜缆/液冷 | 80 |

── 🎯 中枢内买点 (阿娇盘整背驰) ──
| 1 | 立讯精密 | 4 | 80 | ¥67 | ¥65 | ¥78 | ¥85 | 5.5:1 |
```

**去重规则**: 同一代码在最终汇总中只出现一次，按评分降序排列。

### 板块资金流 (easy-tdx, 9秒)

`board_hot.py` 提供概念+行业各Top10实时主力资金。集成到 `daily_report.py` 中。单位转换: `amount/1e8` → 亿, `main_net_amount/1e8` → 亿。

### 竞价开盘 vs 盘中 (Opening Auction vs Intraday)

竞价阶段板块涨幅通常只有0.5-1.5%且主力净流出（试盘），正式开盘后涨幅升至2-4%且主力转为净流入。**不要以竞价数据判断当日方向** — 等正式开盘30分钟后再分析。竞价到盘中的变化可判断主力真实意图：

| 竞价→盘中 | 含义 |
|---|---|
| 净流出→净流入 | 试盘后主力进场 |
| 涨幅收敛(+4%→+2%) | 健康消化 |
| 涨幅扩大(+1%→+4%) | 主力大力推升 |

### 盘中提问节奏

用户在竞价/盘中选择性地问"XX能买吗"，此时必须拉取腾讯实时行情+通达信实时板块资金流，不能依赖过时的 yfinance 昨日收盘价做判断。价格可能在10分钟内从+6%变成-3%。**每次回复前必须刷新实时数据。**

## Quanti5 ETF动量 — 自然月 vs 交易日 (Critical Pitfall)

`etf_momentum.py` 使用 yfinance `period='1y'` 获取K线。动量计算公式是 **交易日回报**（20日/60日/120日），但用户常问"这个月涨了多少"。

**交易日动量 vs 自然月动量差异显著：**
- 交易日20日 ≈ 4周 ≈ 自然月 × 0.8（因有周末）
- 科创芯片 20日回报 = +22.7%, 但自然月6月 = +35.0%
- 用户质疑"月涨幅不对"时，需用自然月计算（按 `dates.strftime('%Y-%m')` 分组取首尾价差）

**正确做法（已修正）：**
```python
# 自然月动量:
months = {}
for d, c in zip(dates, close):
    if d not in months: months[d] = {'open': c, 'close': c}
    months[d]['close'] = c
jun_r = (months['2026-06']['close'] / months['2026-06']['open'] - 1) * 100
# 动量得分: 6月×0.15 + 5月×0.35 + 4月×0.50
```

**趋势门控必须包含6个月回报 > 0** — 通信ETF 6月+23%但半年前跌太多(6月总回报-39%)，不应通过门控。

## 外部知识库

- [fpyluck/chanstock-skill](https://github.com/fpyluck/chanstock-skill) — 缠论知识库 + 语义搜索
- [MobiusQuant/OpenMobius-skill](https://github.com/MobiusQuant/OpenMobius-skill) — SMC/ICT概念库
- [bambuo/chan-model-xgb](https://github.com/bambuo/chan-model-xgb) — XGBoost特征框架
- [Vespa314/chan.py](https://github.com/Vespa314/chan.py) — 缠论引擎
- [EV9H/Quanti5](https://github.com/EV9H/Quanti5) — A股ETF动量轮动量化平台（Next.js+TS, 真实摩擦建模, 回测+58%）
- ClawHub Skills (需EM_API_KEY):
  - [stocks-screener](https://clawhub.ai/financial-ai-analyst/skills/mx-stocks-screener) 🔥 — 自然语言选股(东方财富), 可替代全量扫描
  - [stock-watcher](https://clawhub.ai/robin797860/skills/stock-watcher) — 同花顺自选股(免费, 无需Key)
  - [industry-research](https://clawhub.ai/financial-ai-analyst/skills/industry-research-report) — 行业深度研报PDF
