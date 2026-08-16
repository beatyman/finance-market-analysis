# 专家透镜投委会框架 — 吸收自 AdvancingTitans/stock-analysis

来源：https://github.com/AdvancingTitans/stock-analysis（v5.0.0，A股投资研究系统）

核心机制：**投委会选择（select_committee）** — 根据研究问题自动选择相关专家透镜做对抗分析，而非单框架单结论。

## 15 专家透镜（LENS）

| 透镜ID | 专家 | 关注主题 |
|---|---|---|
| buffett | 巴菲特 | 长期/质量/护城河/现金流/资本配置/治理/估值/分红 |
| munger | 芒格 | 长期/质量/护城河/治理/激励/风险/反向 |
| duan_yongping | 段永平 | 长期/商业模式/品牌/消费者/护城河/现金流/治理 |
| zhang_kun | 张坤 | 长期/质量/现金流/竞争格局/治理/估值/组合 |
| graham | 格雷厄姆 | 估值/安全边际/低估/资产负债/下行/分红 |
| klarman | 卡拉曼 | 估值/安全边际/绝对回报/催化/错定价/下行/风险 |
| lynch | 林奇 | 增长/盈利/收入/产品/用户/估值/景气 |
| o_neil | 欧奈尔 | 增长/盈利加速/行业龙头/趋势/量价/突破/成交量 |
| wood | 木头姐 | 创新/研发/渗透率/技术/增长/长期/产业 |
| dalio | 达利欧 | 宏观/周期/利率/流动性/风险/组合/回撤/波动 |
| soros | 索罗斯 | 预期差/反身性/政策/趋势/催化/景气/拐点 |
| livermore | 利弗莫尔 | 短线/趋势/量价/突破/止损/交易/仓位 |
| minervini | 米勒维尼 | 短线/趋势/量价/突破/盈利加速/强势/止损 |
| simons | 西蒙斯 | 量化/样本/因子/交易成本/波动/回撤/风险/趋势 |
| feng_liu | 冯柳 | 预期差/赔率/催化/困境反转/边际变化/估值/趋势 |

## 对抗分析模式

`LensEngine` 支持四种模式：
- **single** — 单透镜
- **committee** — 投委会（根据问题自动选多个透镜）
- **adversarial** — 对抗（恰好2个透镜，如巴菲特 vs 索罗斯）
- **parallel** — 并行（≥2个透镜）

对抗分析输出：两套独立框架、分歧补证、冲突假设、未来胜负信号。

## 8 研究模块（个股 COMPANY_RESEARCH_MODULE_TOPICS）

| 模块 | 关注 |
|---|---|
| C1 | 商业模式/生意/客户/产品定位/怎么赚钱 |
| C2 | 财务/现金流/利润/盈利/资产负债/自由现金流/ROE |
| C3 | 增长/景气/盈利加速/收入增长/渗透率/创新/产业 |
| C4 | 护城河/竞争/品牌/市场份额/定价权/渠道 |
| C5 | 管理层/治理/资本配置/分红/回购/激励 |
| C6 | 估值/安全边际/低估/赔率/市值/目标价 |
| C7 | 风险/下行/波动/回撤/流动性/交易成本/止损 |
| C8 | 催化/预期差/反身性/政策/跟踪/拐点 |

## 与 a-share-market-analysis 的整合用法

现有体系是**技术面**（缠论+XGBoost+四框架+板块+宏观），stock-analysis 提供**基本面多专家视角**。两者互补：

1. **冯柳透镜（feng_liu）** — "预期差/赔率/困境反转/边际变化" 与用户核心哲学"安全边界/预期差"高度契合，用于筛选"困境反转"标的（如铜陵有色二买、江铜一买这类周期底部）
2. **利弗莫尔/米勒维尼透镜** — 趋势/量价/止损/仓位，与"破位必减仓"、"高手比仓位"一致
3. **格雷厄姆/卡拉曼透镜** — 安全边际，与"安全边界决定执行"一致
4. **达利欧透镜** — 宏观/周期/流动性，与宏观框架互补

## 投委会选择逻辑（select_committee 核心）

```python
LENS_SELECTION_ORDER = (
    "buffett", "munger", "duan_yongping", "zhang_kun", "graham", "klarman",
    "lynch", "o_neil", "wood", "dalio", "soros", "livermore", "minervini",
    "simons", "feng_liu",
)

def select_committee(question, asset_type="company"):
    # 对每个透镜，统计其主题词在研究问题中出现的次数
    scores = {lens_id: sum(3 if topic in question else 0 for topic in topics)
              for lens_id, topics in LENS_TOPICS.items()}
    # 关键词 boost（估值/安全边际 → graham/klarman 等）
    # 按分数降序返回命中透镜
    ranked = sorted(LENS_SELECTION_ORDER, key=lambda lid: (-scores[lid], LENS_SELECTION_ORDER.index(lid)))
    return tuple(ranked[:N])  # N 由 depth 决定
```

## 投资论文版本化（thesis.py）

- `create_thesis` — 创建投资论文
- `review_thesis` — 复核（证据变化检测）
- `update_thesis` — 更新（带版本）
- `invalidate_thesis` — 失效（破位/逻辑破坏）
- `compare_theses` — 版本对比

用途：把"为什么买这只票"固化为可复算、可跟踪、可失效的论文，而非临时观点。
