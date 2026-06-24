#!/usr/bin/env python3
"""Small stdlib-only CLI for the embedded Chanlun generated knowledge files."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, NoReturn


SKILL_ROOT = Path(__file__).resolve().parents[1]
GENERATED_DIR = SKILL_ROOT / "references" / "chanlun" / "kb" / "generated"
FULLTEXT_PATH = GENERATED_DIR / "chanlun.fulltext.jsonl"
VISUAL_PATH = GENERATED_DIR / "chanlun.visual.json"


ID_FIELDS = ("chunk_id", "chunkId", "id", "chunk")
TITLE_FIELDS = ("title", "heading", "section", "source", "path")
TEXT_FIELDS = ("text", "content", "body", "summary", "markdown")


def fail(message: str, code: int = 1) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def require_file(path: Path, description: str) -> None:
    if path.exists():
        if not path.is_file():
            fail(f"{description} exists but is not a file: {path}", 2)
        return
    fail(
        f"missing {description}: {path}\n"
        "Generate the Chanlun KB files first, then rerun this command.",
        2,
    )


def load_fulltext() -> list[dict[str, Any]]:
    require_file(FULLTEXT_PATH, "Chanlun fulltext JSONL")
    records: list[dict[str, Any]] = []
    with FULLTEXT_PATH.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                fail(f"invalid JSON in {FULLTEXT_PATH}:{lineno}: {exc}", 2)
            if not isinstance(value, dict):
                fail(f"expected JSON object in {FULLTEXT_PATH}:{lineno}", 2)
            value.setdefault("_line", lineno)
            records.append(value)
    return records


def load_visual() -> Any:
    require_file(VISUAL_PATH, "Chanlun visual JSON")
    try:
        with VISUAL_PATH.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON in {VISUAL_PATH}: {exc}", 2)


def compact_text(value: Any) -> str:
    parts: list[str] = []

    def walk(item: Any) -> None:
        if item is None:
            return
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, (int, float, bool)):
            parts.append(str(item))
        elif isinstance(item, dict):
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def first_field(record: dict[str, Any], names: Iterable[str]) -> str | None:
    for name in names:
        value = record.get(name)
        if value is not None:
            return str(value)
    return None


def chunk_id(record: dict[str, Any]) -> str:
    return first_field(record, ID_FIELDS) or f"line:{record.get('_line', '?')}"


def title(record: dict[str, Any]) -> str:
    return first_field(record, TITLE_FIELDS) or ""


def body_text(record: dict[str, Any]) -> str:
    for name in TEXT_FIELDS:
        value = record.get(name)
        if isinstance(value, str) and value.strip():
            return value
    return compact_text(record)


def normalize(text: str) -> str:
    return text.casefold()


def query_terms(query: str) -> list[str]:
    folded = normalize(query)
    terms: set[str] = set()
    for token in re.findall(r"[a-z0-9_./:-]+|[\u4e00-\u9fff]+", folded):
        terms.add(token)
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            for size in (2, 3, 4):
                if len(token) >= size:
                    terms.update(token[i : i + size] for i in range(len(token) - size + 1))
        elif len(token) > 3:
            terms.add(token.rstrip("s"))
    return sorted(terms, key=lambda item: (-len(item), item))


def score_record(record: dict[str, Any], query: str, terms: list[str]) -> tuple[float, list[str]]:
    haystack = normalize(compact_text(record))
    title_text = normalize(title(record))
    score = 0.0
    reasons: list[str] = []
    folded_query = normalize(query).strip()

    if folded_query and folded_query in haystack:
        score += 80 + min(len(folded_query), 40)
        reasons.append("exact")

    for term in terms:
        count = haystack.count(term)
        if not count:
            continue
        weight = 2.0 + min(len(term), 8)
        if term in title_text:
            weight *= 2.5
        score += min(count, 8) * weight
        reasons.append(term)

    return score, reasons[:8]


def make_snippet(text: str, query: str, terms: list[str], size: int = 180) -> str:
    folded = normalize(text)
    needles = [normalize(query).strip(), *terms]
    start = -1
    for needle in needles:
        if not needle:
            continue
        start = folded.find(needle)
        if start >= 0:
            break
    if start < 0:
        start = 0
    left = max(0, start - size // 3)
    right = min(len(text), left + size)
    snippet = re.sub(r"\s+", " ", text[left:right]).strip()
    if left > 0:
        snippet = "..." + snippet
    if right < len(text):
        snippet += "..."
    return snippet


def json_dump(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def command_search(args: argparse.Namespace) -> None:
    records = load_fulltext()
    terms = query_terms(args.query)
    ranked = []
    for record in records:
        score, reasons = score_record(record, args.query, terms)
        if score <= 0:
            continue
        text = body_text(record)
        ranked.append(
            {
                "score": round(score, 3),
                "chunk_id": chunk_id(record),
                "title": title(record),
                "snippet": make_snippet(text, args.query, terms),
                "reasons": reasons,
                "source": record.get("source"),
                "path": record.get("path"),
                "page_start": record.get("page_start"),
                "page_end": record.get("page_end"),
                "lesson": record.get("lesson"),
                "lesson_title": record.get("lesson_title"),
                "concepts": record.get("concepts", []),
                "record": record if getattr(args, "include_record", False) else None,
            }
        )
    ranked.sort(key=lambda item: (-item["score"], item["chunk_id"]))
    results = ranked[: args.top_k]

    if args.as_json:
        if not getattr(args, "include_record", False):
            for item in results:
                item.pop("record", None)
        json_dump({"query": args.query, "top_k": args.top_k, "count": len(results), "results": results})
        return

    if not results:
        print("No matches.")
        return
    for index, item in enumerate(results, start=1):
        heading = item["title"] or item["chunk_id"]
        print(f"{index}. {heading} [{item['chunk_id']}] score={item['score']}")
        print(f"   {item['snippet']}")


def command_chunk(args: argparse.Namespace) -> None:
    records = load_fulltext()
    for record in records:
        if chunk_id(record) == args.chunk_id:
            json_dump(record)
            return
    fail(f"chunk not found: {args.chunk_id}", 3)


def visual_records(value: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    def add(key: str, data: Any, kind: str) -> None:
        records.append({"key": key, "kind": kind, "data": data, "text": compact_text({key: data})})

    if isinstance(value, dict):
        for group_name in ("concepts", "visual_cards", "cards", "figures"):
            group = value.get(group_name)
            if isinstance(group, dict):
                for key, data in group.items():
                    add(str(key), data, group_name)
            elif isinstance(group, list):
                for idx, data in enumerate(group):
                    key = first_field(data, ("key", "id", "name", "concept")) if isinstance(data, dict) else None
                    add(key or f"{group_name}:{idx}", data, group_name)
        if not records:
            for key, data in value.items():
                add(str(key), data, "root")
    elif isinstance(value, list):
        for idx, data in enumerate(value):
            key = first_field(data, ("key", "id", "name", "concept")) if isinstance(data, dict) else None
            add(key or str(idx), data, "list")
    else:
        add("visual", value, "root")
    return records


def command_visual(args: argparse.Namespace) -> None:
    data = load_visual()
    records = visual_records(data)
    query = args.concept_or_query
    folded = normalize(query)
    terms = query_terms(query)

    exact = [item for item in records if normalize(item["key"]) == folded]
    if exact:
        matches = [{k: v for k, v in item.items() if k != "text"} for item in exact]
    else:
        ranked = []
        for item in records:
            haystack = normalize(item["text"])
            score = 0.0
            if folded and folded in haystack:
                score += 50 + min(len(folded), 30)
            for term in terms:
                if term in haystack:
                    score += 2 + min(len(term), 8)
            if score > 0:
                ranked.append({**{k: v for k, v in item.items() if k != "text"}, "score": round(score, 3)})
        ranked.sort(key=lambda item: (-item["score"], item["key"]))
        matches = ranked

    output = {"query": query, "count": len(matches), "matches": matches}
    if args.as_json:
        json_dump(output)
        return

    if not matches:
        print("No visual matches.")
        return
    for item in matches:
        score = f" score={item['score']}" if "score" in item else ""
        print(f"{item['key']} ({item['kind']}){score}")
        print(f"  {compact_text(item['data'])[:240]}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search generated Chanlun KB files bundled with the agent-stock skill."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    search = subparsers.add_parser("search", help="search chanlun.fulltext.jsonl")
    search.add_argument("query")
    search.add_argument("--top-k", type=int, default=5)
    search.add_argument("--json", dest="as_json", action="store_true")
    search.add_argument("--include-record", action="store_true", help="include full raw records in JSON output")
    search.set_defaults(func=command_search)

    visual = subparsers.add_parser("visual", help="search chanlun.visual.json")
    visual.add_argument("concept_or_query")
    visual.add_argument("--json", dest="as_json", action="store_true")
    visual.set_defaults(func=command_visual)

    chunk = subparsers.add_parser("chunk", help="print one fulltext chunk by id")
    chunk.add_argument("chunk_id")
    chunk.set_defaults(func=command_chunk)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "top_k", 1) < 1:
        fail("--top-k must be >= 1", 2)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
