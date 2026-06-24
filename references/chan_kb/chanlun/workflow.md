# Chanlun Workflow

## 使用边界

本模块基于用户提供的走势描述或 `stock detail` 输出中的价格序列进行缠论结构推导。
模型不自动读取真实 K 线图、不自动画线、不替代人工复核。分型、笔、线段、
中枢、背驰和买卖点结论均为参考性结构判断，必须列出依据、置信度和失效条件。

当数据不足以确认级别时，必须声明「缠论结构置信度受限」，只输出能确认的较低阶
结论，不强行给出笔、线段或中枢。

## Trigger

Use this workflow when the user asks for:

- 缠论分析、缠论交易决策、缠论选股、缠论复盘
- 中枢、背驰、分型、笔、线段、三买三卖、区间套

## Data Commands

For a single stock:

```bash
stock detail <symbol>
```

For market context:

```bash
stock index
```

For quant-assisted decision:

```bash
stock quant <symbol>
```

For screening:

```bash
stock rank --sort netMainIn --count 50
stock query "<condition>"
```

For final screened candidates that need Chanlun structure:

```bash
stock detail <symbol>
```

If the user provides a chart image or screenshot, compare its visible pattern with
`figures/*.svg` only as a qualitative shape reference. State which card was used,
what matched, what did not match, and whether confidence is limited by missing OHLC
or timeframe data. Do not claim exact automatic K-line recognition from the image.

## Step 1: Define Operating Level

Choose one primary level and one confirmation level.

| User intent | Primary level | Confirmation level |
|---|---:|---:|
| intraday / T | 5m | 1m or 15m |
| ultra-short 1-3 days | 30m | 5m |
| swing 3-10 days | daily | 30m |
| medium-term | weekly | daily |

If `stock detail` lacks enough history:

- daily bars < 30: only discuss recent fractal tendency and moving-average context.
- 5m bars < 30: do not claim segment or center completion on 5m.
- missing intraday bars: use daily structure and state intraday timing is unavailable.

## Step 2: Build Structural Map

Use `rules.md` in this order:

1. Normalize inclusion relationships when explicit OHLC bars are available.
2. Identify top/bottom fractals.
3. Connect valid adjacent opposite fractals into strokes.
4. Group strokes into segments.
5. Locate centers from overlapping same-level moves.
6. Classify the structure as trend, consolidation, center oscillation, or unclear.
7. Check divergence only after the required trend/center conditions are met.

When the raw `stock` output is summarized text instead of full OHLC arrays, do not pretend
precise stroke/segment drawing. Use phrases such as:

- "日线层面存在底分型尝试，但笔尚未确认"
- "30m 中枢可能在扩展，需回看实际 K 线确认"
- "当前数据不足以确认第三类买点"

## Step 3: Locate Buy/Sell Point

Use this priority:

1. First-class buy/sell point: trend divergence after at least two same-level centers.
2. Second-class buy/sell point: center oscillation extreme after first-class reaction.
3. Third-class buy/sell point: break away from center, then pullback without re-entering.
4. No valid buy/sell point: wait, even if money flow or news is strong.

For any buy/sell point, output:

- operating level
- structure type
- buy/sell point type
- trigger price or zone
- invalidation condition
- confidence: high / medium / low
- data limits

## Step 4: Fuse With Agent Stock Data

After structural judgment, use `fusion.md`:

- money flow confirms or weakens the structure
- sector rotation decides whether the signal has market resonance
- news/policy/fundamental context explains why money may continue or fail
- market state from `stock index` caps position size

## Step 5: Decision

Embed a `缠论结构确认` block in the main answer when Chanlun is triggered.

Required fields:

```markdown
## 缠论结构确认

- 操作级别：[5m/30m/日线/周线]
- 走势定位：[趋势/盘整/中枢震荡/结构不清]
- 买卖点：[一买/二买/三买/一卖/二卖/三卖/无]
- 结构依据：[2-4 条，含分型/笔/线段/中枢/背驰]
- 图形参照：[figures/...svg 或 -]
- 置信度：[高/中/低]
- 失效条件：[跌回中枢/跌破分型低点/突破失败/数据不足等]
- 来源锚点：[index.json 中相关 concept 的 source_pages；无需追溯时可写 -]
```

Then convert the result into:

- action
- position size
- buy zone or sell zone
- stop price
- target price
- holding period
- risks

## Step 6: Save

If the caller requires a persisted artifact, follow that caller's path contract.
Otherwise return the structured Chanlun answer only.
