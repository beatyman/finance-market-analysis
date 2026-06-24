#!/usr/bin/env python3
"""Run lightweight retrieval evals for the Chanlun KB."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import chanlun_kb_search as search


SKILL_ROOT = Path(__file__).resolve().parents[1]
KB_ROOT = SKILL_ROOT / "references" / "chanlun" / "kb"
RETRIEVAL_CASES = KB_ROOT / "evals" / "retrieval_cases.jsonl"
TOP_K_REQUIRED = 2


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"invalid JSONL {path}:{lineno}: {exc}") from exc
    return records


def top_search(query: str, top_k: int, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    terms = search.query_terms(query)
    ranked = []
    for record in records:
        score, reasons = search.score_record(record, query, terms)
        if score <= 0:
            continue
        ranked.append(
            {
                "score": score,
                "chunk_id": search.chunk_id(record),
                "page_start": record.get("page_start"),
                "page_end": record.get("page_end"),
                "title": search.title(record),
                "reasons": reasons,
            }
        )
    ranked.sort(key=lambda item: (-item["score"], item["chunk_id"]))
    return ranked[:top_k]


def top_visual(query: str, data: Any) -> list[dict[str, Any]]:
    records = search.visual_records(data)
    terms = search.query_terms(query)
    folded = search.normalize(query)
    ranked = []
    for item in records:
        haystack = search.normalize(item["text"])
        score = 0.0
        if folded and folded in haystack:
            score += 50 + min(len(folded), 30)
        for term in terms:
            if term in haystack:
                score += 2 + min(len(term), 8)
        if score > 0:
            ranked.append({"key": item["key"], "score": score})
    ranked.sort(key=lambda item: (-item["score"], item["key"]))
    return ranked


def page_hit(result: dict[str, Any], expected_pages: list[int]) -> bool:
    start = result.get("page_start")
    end = result.get("page_end") or start
    if not isinstance(start, int):
        return False
    return any(start <= page <= end for page in expected_pages)


def run_case(case: dict[str, Any], top_k: int, records: list[dict[str, Any]], visual_data: Any) -> dict[str, Any]:
    query = case["query"]
    expected_pages = case.get("expected_top_pages") or []
    expected_visual = case.get("expected_visual")
    results = top_search(query, top_k, records)
    visual = top_visual(query, visual_data)

    page_ok = True
    if expected_pages:
        page_ok = any(page_hit(result, expected_pages) for result in results[:TOP_K_REQUIRED])

    visual_ok = True
    if expected_visual:
        visual_ok = bool(visual and visual[0]["key"] == expected_visual)

    top1_ok = bool(results and page_hit(results[0], expected_pages)) if expected_pages else True
    top2_ok = bool(len(results) >= TOP_K_REQUIRED and any(page_hit(result, expected_pages) for result in results[:TOP_K_REQUIRED])) if expected_pages else True
    passed = page_ok and visual_ok and top2_ok
    return {
        "id": case.get("id"),
        "query": query,
        "passed": passed,
        "page_ok": page_ok,
        "visual_ok": visual_ok,
        "top1_ok": top1_ok,
        "top2_ok": top2_ok,
        "expected_top_pages": expected_pages,
        "top_pages": [item.get("page_start") for item in results],
        "expected_visual": expected_visual,
        "top_visual": visual[0]["key"] if visual else None,
        "top_chunks": [item["chunk_id"] for item in results],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Chanlun KB retrieval evals.")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    cases = load_jsonl(RETRIEVAL_CASES)
    records = search.load_fulltext()
    visual_data = search.load_visual()
    results = [run_case(case, args.top_k, records, visual_data) for case in cases]
    passed = sum(1 for item in results if item["passed"])
    failed = len(results) - passed
    summary = {"passed": passed, "failed": failed, "total": len(results), "results": results}

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"Chanlun KB eval: {passed}/{len(results)} passed")
        for item in results:
            status = "PASS" if item["passed"] else "FAIL"
            print(f"- {status} {item['id']}: top_pages={item['top_pages']} top_visual={item['top_visual']}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
