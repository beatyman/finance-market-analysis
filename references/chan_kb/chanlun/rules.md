# Chanlun Rules

This file is the compact rule layer. Keep it operational and bounded.

## 1. Level And Completion

Source anchors: p82, p313, p344, p363.

- Every structure must name its level first.
- Any level decomposes into trend or consolidation.
- Trend and consolidation are observed as they unfold; do not force prediction.
- Ambiguity is allowed, but it is not looseness: list each valid interpretation and choose the one that best supports action.

## 2. Inclusion Processing

Source anchors: p569, p640, p765.

Before identifying fractals from OHLC bars, process inclusion relationships:

1. If a bar contains the next bar, or is contained by it, merge according to current direction.
2. In an up move, keep the higher high and higher low.
3. In a down move, keep the lower high and lower low.

If direction is unclear, state that inclusion processing cannot be resolved.

Visual reference: `figures/fractal_stroke.svg`.

## 3. Fractal

Source anchor: p569.

- Top fractal: the middle bar has the highest high among three adjacent bars, and its low is also higher than the adjacent lows.
- Bottom fractal: the middle bar has the lowest low among three adjacent bars, and its high is also lower than the adjacent highs.
- A single fractal is only a local structure. It is not a buy/sell point by itself.

## 4. Stroke

Source anchors: p569, p765.

- A stroke connects adjacent opposite fractals after inclusion processing.
- A valid stroke should have enough separation. Use at least 5 processed K bars as the practical minimum.
- Consecutive same-type fractals require filtering:
  - for multiple tops, keep the stronger/later valid top according to direction
  - for multiple bottoms, keep the stronger/later valid bottom according to direction
- If K-bar depth is insufficient, only report fractal tendency, not a confirmed stroke.

Visual reference: `figures/fractal_stroke.svg`.

## 5. Segment

Source anchors: p611, p640, p704, p812.

- A segment is composed of at least three strokes.
- A segment is not ended by a simple price poke. It requires segment-level break evidence.
- Use characteristic sequence logic: discuss whether the opposite strokes form a valid break sequence.
- A prior segment is confirmed broken when the new movement forms a valid sequence beyond the old segment.
- Do not use center rules below segment level when there is no valid center.

Visual reference: `figures/segment_break.svg`.

## 6. Center

Source anchors: p121, p122, p313, p992.

A center is the overlapping price zone of at least three consecutive same-level movements.

For three moves, define:

- `ZG = min(high_1, high_2, high_3)`
- `ZD = max(low_1, low_2, low_3)`
- A center exists when `ZD <= ZG`.

Center states:

- extension: more same-level moves oscillate around the same center
- new same-level center: a later center has no overlap with the prior center
- expansion: interactions with prior center territory create a larger-level center
- upgrade: after 5 extensions, treat the structure as likely larger-level center formation

Visual reference: `figures/center_zg_zd.svg`.

## 7. Trend And Consolidation

Source anchors: p56, p82, p121, p313.

- A trend needs at least two same-level centers in the same direction.
- A single center with oscillation is consolidation.
- No trend, no true divergence. If only one center exists, call it consolidation divergence at most.

## 8. Divergence

Source anchors: p56, p177, p194, p231, p352, p403, p410.

Check divergence only after the structure qualifies:

- true divergence: occurs in a trend, normally after the second same-level center or later
- consolidation divergence: an attempt to leave a center fails and returns
- MACD area, histogram length, and zero-axis pullback are auxiliary evidence, not the primary rule
- compare same-level movement strength; do not compare unrelated levels

Bullish divergence is only actionable when it maps to a valid buy point and risk can be defined.
Bearish divergence overrides optimistic news or money flow.

Visual reference: `figures/divergence_macd.svg`.

## 9. Buy/Sell Points

Source anchors: p135, p231, p491, p555, p992.

First-class buy/sell point:

- appears around trend divergence
- strongest when level is clear and the prior trend has at least two centers

Second-class buy/sell point:

- follows the first-class reaction
- often appears near center oscillation extremes or a retest

Third-class buy/sell point:

- price breaks away from the center
- then pulls back without re-entering the center
- the invalidation is re-entry into the old center

No buy point means no buying, even if the stock is hot.
No sell point does not mean ignore risk; position size and invalidation still apply.

Visual reference: `figures/buy_sell_points.svg`.

## 10. Interval Nesting

Source anchors: p555, p304.

Interval nesting means using a larger-level structure to choose direction, then a smaller-level structure to time the entry.

Example:

- daily structure has a possible second buy
- 30m confirms a center no longer breaks down
- 5m shows a pullback divergence or third buy

If the smaller level contradicts the larger level, reduce position or wait.

Visual reference: `figures/interval_nesting.svg`.

## 11. Risk And Capital

Source anchors: p219, p283, p417, p733.

- Risk first: if the market gives no time to correct a mistake, avoid the trade.
- Use pressure-free capital. Do not borrow or over-leverage.
- A buy point defines risk; a story does not.
- If structure confidence is low, cap the position to observation or micro test.
- If a sell point or invalidation appears, execute before explaining.

## 12. Confidence

High confidence:

- clear level, enough bars, valid center/segment, buy/sell point and invalidation align

Medium confidence:

- structure mostly clear, but one level or one sequence needs chart confirmation

Low confidence:

- insufficient bars, conflicting level interpretations, or summarized data only

When confidence is low, do not output aggressive action.
