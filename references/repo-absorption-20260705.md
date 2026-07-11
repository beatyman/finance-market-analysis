# GitHub仓库吸收全部记录 (至2026-07-06)

## ✅ 已吸收为代码模块 (5个)

| 仓库 | 模块 | 行数 | 核心价值 |
|------|------|------|---------|
| TradeHelper | `trade_helper.py` | 400 | 1/3/5日概率预测+数据质量闸门+市场状态 |
| Stocks-Master等4合1 | `enhanced_tools.py` v1 | 663 | 宏观NLP+左侧支撑+横截面排名+信号衰减 |
| AStockV4-Systems | V4.5经验因子 | +210 | 47K样本回测17条买卖/规避规则 |
| stock_scorer | G/Z/K/S六维打分 | +216 | 六维打分+市场环境自适应权重+0~10分 |
| cn_stock_scan | `smc_ict.py` | 806 | OB/FVG/PDA+三重背离+三推75%, 原版忠实移植 |
| a-share-quant-sim | 连板辨识度 | +120 | 涨停记忆×时间衰减(A股独有) |
| cxdata-mainline-agent | 主线识别 | +120 | 四维综合评分+情绪周期(冰点↔高潮) |

## 🟡 方法论吸收 (4个)

| 来源 | 概念 | 应用 |
|------|------|------|
| stock-research-skill | 三段论推导+逆向思辨 | 融入质检清单 |
| astock-quant | 横截面排名防look-ahead | factor_screen.py/scorer.py |
| BAISYS_QUANT | 信号衰减模型 | enhanced_tools.py |
| UZI-Skill | 13项自检Gate(R5+W6+I2) | SKILL.md输出前强制检查 |

## ❌ 未吸收 (18个)

| 仓库 | 原因 |
|------|------|
| GTJA190 | 因子重叠+需商业数据源 |
| shaijin-select | 选股过滤,与阿娇重叠 |
| stock-analysis (maxwu) | 100+文件个人系统 |
| fast-knife-engine | 依赖新浪/龙虎榜API不兼容 |
| TradingAgentsAstockMcp | MCP数据服务层 |
| 寻龙诀 | 商业付费文档 |
| dragon-tiger-tracker | 需akshare+SQLite |
| tradingagents-akshare | 数据源迁移 |
| UZI-Skill | AI提示词模板 |
| A-Stock-Skills | Claude技能库 |
| a-share-technical-analysis | Codex技能 |
| shares-web | Web前端 |
| AIAlpha | 需tick数据 |
| a-stock-data | 数据基础设施 |
| strong-stock-screener | 商业API依赖 |
| dao-quant-research | 纯文档 |
| FactorZen | Rust CLI太重 |
| quant-showcase/SerenityMonitor/stockdata/astock-peg/stock-query | 功能重叠 |

## 关键教训 (已写入SKILL.md规则6-7)

1. **吸收必须忠实原版** — SMC/ICT初版自创跳过R3→用户纠正→重写
2. **Repo评估快速否决** — 批量推送时每repo一行判断
3. **功能重叠优先跳过** — 因子库/选股器重叠不吸收
4. **数据依赖是红线** — 商业API的模块不可吸收
