# 外部 Skill Review 方法论

> 2026-06-25 | 本轮会话吸收 ClawHub 10+ 个金融 Skill 的设计精华

## Review 框架

| 维度 | 评分标准 |
|---|---|
| 数据源 | 是否免费/需Key/延迟/可靠性 |
| 设计模式 | 持仓管理/预警系统/分时量能/图表 |
| A股适用 | 直接可用/需改造/不适用 |
| 集成难度 | 即插即用/需改造/需Key |

## 已吸收的精华

| 来源 | 设计 | 集成到 |
|---|---|---|
| stock-watcher (同花顺/免费) | 自选股管理+免费行情 | `portfolio.py` |
| stock-monitor (7规则预警) | 分级预警🔴🟡🔵+红涨绿跌 | `portfolio.py` |
| a-stock-analysis (新浪/免费) | 分时量能+主力动向 | `volume_minute.py` |
| Quanti5 (ETF动量) | 自然月动量+趋势门+仓位调节 | `etf_momentum.py` |

## 设计模式对照

| 他们的模式 | 我们的实现 |
|---|---|
| 持仓: add/remove/show/alerts | `portfolio.py add 002475 --cost 67 --qty 1000` |
| 预警: 成本%/日内%/均线/RSI/放量/动态止盈 | `portfolio.py alerts` |
| 分时: 早盘30分/尾盘/放量TOP10/主力判断 | `volume_minute.py 603019` |
| 动量: 混合窗口+趋势门+仓位分配 | `etf_momentum.py` |

## 未吸收（需API Key）

| Skill | Key | 价值 |
|---|---|---|
| stocks-screener (东方财富) | EM_API_KEY | 自然语言选股秒级 |
| financial-data (东方财富) | EM_API_KEY | 实时行情+财务 |
| industry-research (东方财富) | EM_API_KEY | 行业深度研报PDF |
| tushare-finance | Tushare Token | 220+数据接口 |

## 设计原则

1. **免费优先** — 先集成不需要Key的
2. **吸收设计模式，不改核心算法** — 缠论+阿娇是独有优势
3. **保持独立可运行** — 每个模块 `python3 xxx.py` 即出结果
4. **数据源标注来源** — 腾讯/新浪/AKShare/baostock
