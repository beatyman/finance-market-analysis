# ClawHub 金融 Skill 审查报告

> 2026-06-25 | 审查14个公开金融Skill | 吸收3个免费Skill设计精华

## 已吸收的免费Skill

| 来源 | 吸收的设计 | 落地模块 |
|---|---|---|
| @cnyezi/a-stock-analysis | 分时量能+主力动向(新浪5分钟K线) | `volume_minute.py` |
| @robin797860/stock-watcher | 同花顺10jqka自选股管理 | `portfolio.py` |
| @thirtyfang/stock-monitor | 7规则分级预警+中国习惯(红涨绿跌) | `portfolio.py` |
| @clawmaker/Quanti5 | ETF动量轮动+真实摩擦建模 | `etf_momentum.py` |

## 需API Key的（待集成）

| Skill | 需Key | 价值 |
|---|---|---|
| stocks-screener (东方财富) | EM_API_KEY | ⭐⭐⭐⭐⭐ 自然语言选股秒级 |
| financial-data (东方财富) | EM_API_KEY | ⭐⭐⭐ 实时行情+财务 |
| industry-research (东方财富) | EM_API_KEY | ⭐⭐⭐ 行业PDF研报 |

## 已在使用/价值有限的

| Skill | 结论 |
|---|---|
| akshare-stock | ✅ 已在使用 |
| tushare-finance | 需Tushare Token(注册即用) |
| stock-analysis (yfinance) | 美股为主, 价值有限 |
| stock-market-pro (yfinance) | 图表工具, 非A股 |
| china-stock-analysis | 太基础, web search查价 |
| crypto-market-data | Node.js/CoinGecko, 已有yfinance替代 |
| stock-info-explorer | 与market-pro重复 |
| stock-monitor | ✅ 已吸收预警设计 |
| eastmoney skills | 需EM_API_KEY |

## 关键教训

1. **ClawHub skill不在GitHub** — 通过OpenClaw registry发布，直接clone不可行
2. **两个立即可用**: stock-watcher(同花顺/免费) + tushare(注册即用)
3. **分时量能最大发现**: 早盘放量≠主力吸筹 — 300只抢筹中30%是卖出信号
