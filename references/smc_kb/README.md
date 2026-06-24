# knowledge_base/

Structured knowledge cards used by the skill's retrieval-augmented
answers. Two card types:

```
knowledge_base/
├── concepts/    # 380 ICT/SMC trading-concept cards (JSON)
└── cases/       # 584 case-study cards (JSON)
```

## Contents

Each card is a JSON document with a schema-driven structure. Concept
cards carry: identification rules, trading implications, common
mistakes, related concepts. Case cards carry: market context, key
observation, analysis steps, lessons.

The cards are **original structured summaries** authored by this project
from analysis of publicly available educational content (online ICT/SMC
trading tutorials). They are not verbatim copies of source material;
each card paraphrases and re-structures trading concepts into a schema
useful for retrieval-augmented generation.

## Purpose

For research and educational use as a grounding source for AI trading
assistants — to reduce hallucination by retrieving structured,
schema-validated knowledge at query time instead of letting the LLM
guess.

## Build

The vector index lives in `_index/` (gitignored — built by the
installer; not shipped in the source repository).

To rebuild manually:

```bash
cd <skill-dir>
.venv/bin/python scripts/build_index.py
```

## Attribution

If you believe a card contains material that should be removed,
attributed differently, or corrected, please open an issue on the
project repository.

See `../ATTRIBUTION.md` for the project's full third-party attribution.
