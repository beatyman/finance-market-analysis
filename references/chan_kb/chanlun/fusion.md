# Chanlun Fusion With Agent Stock

Chanlun answers: where is the structure and is there a valid buy/sell point?
Agent-stock data answers: is money, sector, news, and market context supporting the structure?

## Evidence Order

1. Market state: `stock index`
2. Stock structure: `stock detail <symbol>` plus `rules.md`
3. Money flow: main inflow/outflow, big orders, 5-day flow trend
4. Sector resonance: industry and concepts
5. News, policy, fundamental context
6. Position sizing and invalidation

## Fusion Matrix

| Chanlun structure | Money flow | Sector/news | Action bias |
|---|---|---|---|
| valid buy point | positive | resonant | normal position within risk cap |
| valid buy point | weak | resonant | half position or wait for intraday confirmation |
| valid buy point | positive | no sector support | micro test, mark as independent money flow |
| no buy point | positive | hot news | do not chase; wait for pullback or third buy |
| center oscillation | mixed | mixed | T operation only if range and cost allow |
| bearish divergence/sell point | any | any | reduce or exit; structure risk overrides narrative |
| unclear structure | any | any | observe; no structural recommendation |

## Structural Score Modifier

When a downstream flow needs a small numeric adjustment, use only structural signals:

- confirmed buy point with money/sector support: `+5`
- possible buy point but low confidence: `+2`
- unclear structure: `0`
- center re-entry after third-buy attempt: `-3`
- confirmed sell point or bearish divergence: `-5`

Do not let the modifier override a hard risk rule. A confirmed sell point, bearish divergence,
third-buy failure back into the center, or structural invalidation is also a behavioral gate:
even if the parent score remains in a buy range after the numeric modifier, downgrade the
action to observe/reduce/exit unless the user explicitly asks for non-structural speculation.

## Fundamental And News Context

Source anchors: p18, p25, p219, p304, p733, p851.

Fundamental and news factors are catalysts and risk context, not replacement signals.
For ultra-short decisions, fundamentals are checked before scoring as veto/context, not as
a positive weight that can compensate for weak money flow or missing structure.
Use them to answer:

- What does the market likely believe about this stock?
- Is the event strong enough to attract sustained money?
- Is the news already priced into a high-level sell point?
- Is policy risk large enough to lower position size?
- Is there a fundamental/event risk that should block new buying before structure is considered?

If news is bullish but structure is extended or divergent, treat it as possible distribution.
If news is bearish but the stock refuses to break structure, mark it as strength, not automatic buy.

## Sector Rotation

Source anchors: p1199, p1202.

For screening, combine Chanlun with sector rotation:

1. Use `stock index` to identify leading sectors and market breadth.
2. Use `stock rank` or `stock query` to form a candidate pool.
3. Prefer stocks whose structure is earlier than the sector crowd:
   - fresh center break
   - pullback not re-entering center
   - first center upshift
4. Avoid stocks that are already near high-level sell points, even if ranking is strong.

## Position Sizing

| Structure confidence | Market state | Suggested cap |
|---|---|---:|
| high | strong / bullish oscillation | existing cap |
| high | weak market | half of normal cap |
| medium | any | micro or test position |
| low | any | no new position |
| sell point | any | reduce / exit |

The surrounding task's risk rules still apply.
If the parent score says buy but Chanlun has no buy point, low confidence, or invalidation
nearby, downgrade the action to wait or micro observation unless the user explicitly asks
for non-structural speculation.
