# Agent Stock Chanlun Package

This directory is the embedded Chanlun knowledge package for `agent-stock`.
It must travel with the skill and run independently from any external RAG
runtime, Qdrant, the source PDF, or any external knowledgebase.

## Files

- `workflow.md`: how to run Chanlun analysis with `stock` CLI data.
- `rules.md`: compact operating rules for levels, fractals, strokes,
  segments, centers, divergence, and buy/sell points.
- `fusion.md`: how Chanlun structure combines with money flow, sectors,
  news, policy, and fundamental context.
- `index.json`: lightweight routing manifest for quick lookup. Paths are
  relative to this directory and include figure usage boundaries.
- `figures/*.svg`: original abstract visual cards for comparison.
- `kb/`: evidence-backed fulltext, visual, graph, manifest, eval, and report
  layer for source-supported answers.

## Visual Assets

The figures are not copied PDF pages. They are simplified comparison cards
created for this skill, so the module remains portable and easy to inspect.

- `figures/fractal_stroke.svg`: top/bottom fractal, inclusion processing,
  and stroke formation.
- `figures/overview.svg`: one-page overview of all visual cards.
- `figures/segment_break.svg`: segment composition and segment break.
- `figures/center_zg_zd.svg`: center overlap area with ZG/ZD labels.
- `figures/buy_sell_points.svg`: first, second, and third buy/sell points.
- `figures/divergence_macd.svg`: trend divergence and MACD auxiliary check.
- `figures/interval_nesting.svg`: large-to-small level entry confirmation.

Use the figures as shape references, not as automatic chart recognition.
When the live data is numeric text instead of chart images, reason from the
price sequence and state uncertainty.

## Deep KB

Use `kb/` when a question needs original lesson/page support, conflicting rule
context, source snippets, or visual-card routing beyond the fast package.

Common commands from the skill root:

```bash
python3 scripts/chanlun_kb_search.py search "第三类买点 回试 不触及 中枢" --top-k 3
python3 scripts/chanlun_kb_search.py visual "中枢" --json
python3 scripts/chanlun_kb_validate.py
python3 scripts/chanlun_kb_report.py
```

## Source Anchors

The package was distilled from the local PDF `阿娇版+缠论.pdf`. The skill does
not require the PDF at runtime. These anchors are retained only for provenance
and later manual review:

- p56, lesson 15: no trend, no divergence.
- p82, lesson 17: all trends and consolidations complete at their level.
- p121, lesson 20: center formation, extension, expansion, third buy/sell point.
- p135, lesson 21: completeness of buy/sell point analysis.
- p177 and p194, lessons 24-25: MACD as an auxiliary divergence tool.
- p231, lesson 27: consolidation divergence and low-position buy points.
- p283, lesson 31: capital management.
- p301, lesson 32: present-tense thinking.
- p313, lesson 33: ambiguity of trends and centers.
- p352-p363, lessons 37-38: divergence and same-level decomposition.
- p555, lesson 61: interval nesting.
- p569, lesson 62: fractals, strokes, and segments.
- p611 and p640, lessons 65-67: segment rules and characteristic sequences.
- p724-p733, lessons 73-74: opportunity classification and policy risk.
- p992, lesson 92: center oscillation monitor.
- p1199, lesson 106: moving averages, rotation, and sector strength.

## Operating Principle

Chanlun is used here as a structure-confirmation layer. The order is:

1. Identify the operating level and structural position.
2. Check whether a valid buy/sell point exists.
3. Use `stock` data for money flow, sector strength, news, and risk.
4. Convert the combined evidence into position size, stop, target, and invalidation.

No structure, no chase. Strong news, strong money flow, or hot sectors can
raise attention, but they do not replace a valid structure.
