# Chanlun KB Package

This is the evidence-backed Chanlun knowledge package for `agent-stock`.
It complements the fast files in `references/chanlun/`.

## Boundary

The fast package answers routine Chanlun questions quickly:

- `../workflow.md`: when and how to run Chanlun analysis.
- `../rules.md`: compact operating rules.
- `../fusion.md`: how to combine structure with market, money flow, sector,
  news, policy, and fundamentals.
- `../figures/*.svg`: qualitative visual cards.

This KB package answers deeper evidence questions:

- where a rule comes from;
- which page, lesson, or chunk supports an interpretation;
- which visual card is relevant to a concept;
- whether the generated indexes are complete and portable.

The KB is self-contained after build. Runtime use does not require any external
RAG runtime, Qdrant, the source PDF, or the Downloads path.

## Layout

```text
kb/
  manifest.json
  manifest.schema.json
  README.md
  sources/
    source_manifest.json
    normalized/pages.jsonl
  generated/
    chanlun.fulltext.jsonl
    chanlun.visual.json
    chanlun.graph.json
  evals/
    golden_qa.jsonl
    retrieval_cases.jsonl
    negative_cases.jsonl
  reports/
    chanlun_build_report.md
    chanlun_validate_*.md
    chanlun_validate_*.json
```

## PageIndex Build

The active text KB is rebuilt from a PageIndex Markdown tree. This keeps the
runtime portable while using PageIndex at build time for semantic document
structure.

Prepare text and PageIndex Markdown from the PDF:

```bash
python3 scripts/chanlun_pageindex_prepare.py \
  --pdf /path/to/阿娇版+缠论.pdf
```

Then run PageIndex in Markdown mode with node text retained:

```bash
cd references/chanlun/kb/sources/pageindex/pageindex_run
pageindex-run \
  --md_path ../ajiao_chanlun_pageindex.md \
  --if-add-node-summary no \
  --if-add-doc-description no \
  --if-add-node-text yes \
  --if-add-node-id yes
```

Finally rebuild the portable AgentStock KB:

```bash
python3 scripts/chanlun_kb_build.py \
  --source-text references/chanlun/kb/sources/pageindex/ajiao_chanlun_extracted.txt \
  --toc-json references/chanlun/kb/sources/pageindex/toc_lessons.json \
  --pageindex-structure references/chanlun/kb/sources/pageindex/pageindex_run/results/ajiao_chanlun_pageindex_structure.json
```

The source PDF and PageIndex runtime are build inputs only. Generated KB files
travel with the skill. The SVG visual cards and visual-use boundaries are not
rebuilt by PageIndex; they remain the existing qualitative visual package.

## Search

Use the stdlib-only search CLI:

```bash
python3 scripts/chanlun_kb_search.py search "第三类买点 回试 不触及 中枢" --top-k 3
python3 scripts/chanlun_kb_search.py visual "中枢" --json
python3 scripts/chanlun_kb_search.py chunk pdf.p0123.02
```

Default JSON search output is intentionally light. Use `chunk <chunk_id>` or
`search --include-record --json` only when the full record is needed.

## Validate And Report

```bash
python3 scripts/chanlun_kb_validate.py
python3 scripts/chanlun_kb_report.py --json
```

Validation checks that:

- generated indexes exist and parse;
- manifest assets are relative and present;
- sha256 and size match;
- each concept has source pages and rule/chunk references;
- required output fields are present;
- SVG cards carry title/desc and visual-use boundaries.

Reports are written to `reports/`.

## Answer Policy

Use fast rules first for routine Chanlun structure analysis and screening.
Use the KB when the user asks for source support, original context, lesson/page
evidence, conflict resolution, or complex definitions.

When answering from the KB:

- cite chunk IDs and page/lesson anchors;
- separate source evidence from structural inference;
- mention conflicts or insufficient evidence instead of flattening them;
- lower confidence when OHLC, timeframe, or page evidence is insufficient.

## Visual Boundary

SVG cards are qualitative comparison cards. They can help explain or compare
structure shapes, but they are not automatic K-line recognition templates and
they do not replace OHLC-level confirmation.
