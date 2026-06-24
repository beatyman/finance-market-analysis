#!/usr/bin/env python3
"""Build the portable Chanlun KB indexes for the agent-stock skill.

This script is intentionally stdlib-only. It turns the extracted PDF text,
the fast Chanlun markdown files, and SVG visual cards into a small set of
portable JSON/JSONL indexes that can travel with the skill.
"""

from __future__ import annotations

import argparse
import shutil
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


SKILL_ROOT = Path(__file__).resolve().parents[1]
CHANLUN_ROOT = SKILL_ROOT / "references" / "chanlun"
KB_ROOT = CHANLUN_ROOT / "kb"
GENERATED_DIR = KB_ROOT / "generated"
SOURCES_DIR = KB_ROOT / "sources"
NORMALIZED_DIR = SOURCES_DIR / "normalized"
PAGEINDEX_DIR = SOURCES_DIR / "pageindex"
REPORTS_DIR = KB_ROOT / "reports"
CONCEPT_CHUNK_LIMIT = 200

FAST_FILES = [
    "README.md",
    "workflow.md",
    "rules.md",
    "fusion.md",
    "figures/README.md",
]

OUTPUT_FIELDS = [
    "操作级别",
    "走势定位",
    "买卖点",
    "结构依据",
    "图形参照",
    "置信度",
    "失效条件",
]

VISUAL_BOUNDARY = (
    "Use SVG cards as qualitative shape references only. Do not use them for "
    "automatic K-line recognition, exact measurement, or buy/sell point "
    "declaration without level and invalidation."
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rel(path: Path) -> str:
    return path.resolve().relative_to(SKILL_ROOT.resolve()).as_posix()


def slug(text: str, fallback: str = "chunk") -> str:
    text = re.sub(r"[\s/]+", "-", text.strip().lower())
    text = re.sub(r"[^0-9a-zA-Z_\-\u4e00-\u9fff]+", "", text)
    return text.strip("-") or fallback


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def tokenize(text: str) -> list[str]:
    terms: set[str] = set()
    folded = text.casefold()
    for token in re.findall(r"[a-z0-9_./:-]+|[\u4e00-\u9fff]+", folded):
        if not token:
            continue
        terms.add(token)
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            for size in (2, 3, 4):
                if len(token) >= size:
                    terms.update(token[i : i + size] for i in range(len(token) - size + 1))
        elif len(token) > 4:
            terms.add(token.rstrip("s"))
    return sorted(terms)


def page_numbers_from_text(text: str) -> list[int]:
    numbers = [int(item) for item in re.findall(r"PDF_PAGE_START:(\d{4})", text)]
    numbers.extend(int(item) for item in re.findall(r"source_page:(\d{1,4})", text))
    for start, end in re.findall(r"page_start:(\d{1,4})\s+page_end:(\d{1,4})", text):
        numbers.extend(range(int(start), int(end) + 1))
    if not numbers:
        title_match = re.search(r"PDF page\s+(\d{4})", text, re.IGNORECASE)
        if title_match:
            numbers.append(int(title_match.group(1)))
    return sorted(set(numbers))


def strip_pageindex_comments(text: str) -> str:
    return re.sub(r"<!--\s*[^>]*-->", "", text).strip()


def parse_lesson_from_hierarchy(hierarchy: list[str], text: str = "") -> tuple[int | None, str | None]:
    haystacks = [*hierarchy, text[:800]]
    for item in haystacks:
        match = re.search(r"lesson-(\d{3})\s+教你炒股票\s+\d+\s*[：:]\s*(.+)", item)
        if match:
            return int(match.group(1)), compact(match.group(2))
        match = re.search(r"lesson\s*:\s*(\d{1,3})", item)
        if match:
            lesson = int(match.group(1))
            title_match = re.search(r"lesson_title\s*:\s*([^<\n]+)", text)
            return lesson, compact(title_match.group(1)) if title_match else None
    return None, None


def load_pageindex_structure(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        structure = data.get("structure", data)
    else:
        structure = data
    if isinstance(structure, dict):
        return [structure]
    if isinstance(structure, list):
        return structure
    raise SystemExit(f"unsupported PageIndex structure shape: {path}")


def walk_pageindex_nodes(nodes: Any, hierarchy: list[str] | None = None) -> list[dict[str, Any]]:
    hierarchy = hierarchy or []
    result: list[dict[str, Any]] = []
    if isinstance(nodes, dict):
        title = str(nodes.get("title") or "")
        children = nodes.get("nodes") or []
        current_hierarchy = [*hierarchy, title] if title else hierarchy
        node = {key: value for key, value in nodes.items() if key != "nodes"}
        node["_hierarchy"] = current_hierarchy
        node["_is_leaf"] = not bool(children)
        result.append(node)
        result.extend(walk_pageindex_nodes(children, current_hierarchy))
    elif isinstance(nodes, list):
        for child in nodes:
            result.extend(walk_pageindex_nodes(child, hierarchy))
    return result


def copy_pageindex_source(path: Path) -> Path:
    PAGEINDEX_DIR.mkdir(parents=True, exist_ok=True)
    destination = PAGEINDEX_DIR / "ajiao_chanlun_pageindex_structure.json"
    if path.resolve() != destination.resolve():
        shutil.copy2(path, destination)
    return destination


def chunk_pageindex_structure(
    pageindex_structure_path: Path,
    concepts: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], Path]:
    copied_structure = copy_pageindex_source(pageindex_structure_path)
    roots = load_pageindex_structure(copied_structure)
    nodes = walk_pageindex_nodes(roots)
    records = []
    normalized_nodes = []
    seen_ids: set[str] = set()

    for index, node in enumerate(nodes, start=1):
        raw_text = str(node.get("text") or "")
        text = strip_pageindex_comments(raw_text)
        if len(text) < 80:
            continue
        title_text = str(node.get("title") or "")
        hierarchy = [str(item) for item in node.get("_hierarchy", []) if item]
        page_numbers = page_numbers_from_text(raw_text + "\n" + title_text)
        lesson, lesson_title = parse_lesson_from_hierarchy(hierarchy, raw_text)
        if lesson_title is None and lesson:
            for item in hierarchy:
                if f"lesson-{lesson:03d}" in item:
                    lesson_title = compact(re.sub(r"^lesson-\d{3}\s+教你炒股票\s+\d+\s*[：:]\s*", "", item))
                    break
        page_start = min(page_numbers) if page_numbers else None
        page_end = max(page_numbers) if page_numbers else page_start
        prefix = f"l{lesson:03d}" if lesson else "front"
        if page_start:
            base_id = f"pageindex.{prefix}.p{page_start:04d}"
            if page_end and page_end != page_start:
                base_id += f"-p{page_end:04d}"
        else:
            base_id = f"pageindex.node{index:04d}"
        chunk_id = base_id
        suffix = 2
        while chunk_id in seen_ids:
            chunk_id = f"{base_id}.{suffix}"
            suffix += 1
        seen_ids.add(chunk_id)

        record = {
            "chunk_id": chunk_id,
            "kind": "pageindex_semantic_node",
            "source": "阿娇版+缠论.pdf via PageIndex Markdown tree",
            "path": rel(copied_structure),
            "title": (
                f"p{page_start}"
                + (f"-p{page_end}" if page_end and page_start and page_end != page_start else "")
                + (f" lesson {lesson}: {lesson_title}" if lesson else "")
            )
            if page_start
            else (title_text or f"PageIndex node {index}"),
            "page_start": page_start,
            "page_end": page_end,
            "lesson": lesson,
            "lesson_title": lesson_title,
            "pageindex_node_id": node.get("node_id"),
            "pageindex_line_num": node.get("line_num"),
            "pageindex_hierarchy": hierarchy,
            "concepts": concepts_from_text(text, concepts),
            "keywords": tokenize("\n".join(hierarchy) + "\n" + text)[:200],
            "text": text,
        }
        records.append(record)
        normalized_nodes.append(
            {
                **record,
                "raw_title": title_text,
                "raw_text": raw_text,
                "is_leaf": node.get("_is_leaf"),
            }
        )

    return normalized_nodes, records, copied_structure


def split_pages(source_text: str) -> list[dict[str, Any]]:
    pages = source_text.split("\f")
    records = []
    for idx, page in enumerate(pages, start=1):
        text = page.strip()
        if not text:
            continue
        records.append({"page": idx, "text": text})
    return records


def load_toc(path: Path | None) -> list[dict[str, Any]]:
    if not path or not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return []
    rows = []
    for row in data:
        try:
            rows.append(
                {
                    "lesson": int(row["lesson"]),
                    "title": str(row["title"]),
                    "date": str(row.get("date", "")),
                    "toc_page": int(row["toc_page"]),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(rows, key=lambda item: item["toc_page"])


def lesson_for_page(page: int, toc: list[dict[str, Any]]) -> dict[str, Any] | None:
    current = None
    for row in toc:
        if page >= row["toc_page"]:
            current = row
        else:
            break
    return current


def windows(text: str, size: int = 900, overlap: int = 120) -> list[tuple[int, int, str]]:
    text = text.strip()
    if len(text) <= size:
        return [(0, len(text), text)]
    parts = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            punct = max(text.rfind("。", start, end), text.rfind("\n", start, end))
            if punct > start + size // 2:
                end = punct + 1
        parts.append((start, end, text[start:end].strip()))
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return parts


def concepts_from_text(text: str, concepts: dict[str, Any]) -> list[str]:
    hits = []
    for cid, info in concepts.items():
        keywords = info.get("keywords") or []
        if any(str(keyword) and str(keyword) in text for keyword in keywords):
            hits.append(cid)
    return hits


def chunk_source_text(
    source_text_path: Path,
    toc: list[dict[str, Any]],
    concepts: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source_text = source_text_path.read_text(encoding="utf-8", errors="ignore")
    pages = split_pages(source_text)
    page_records = []
    chunk_records = []

    for page in pages:
        page_no = page["page"]
        text = page["text"]
        lesson = lesson_for_page(page_no, toc)
        concept_hits = concepts_from_text(text, concepts)
        page_records.append(
            {
                "source_id": "ajiao_chanlun_pdf_text",
                "page": page_no,
                "lesson": lesson["lesson"] if lesson else None,
                "lesson_title": lesson["title"] if lesson else None,
                "char_count": len(text),
                "concepts": concept_hits,
                "text": text,
            }
        )
        for part_idx, (start, end, part) in enumerate(windows(text), start=1):
            if not part:
                continue
            cid = f"pdf.p{page_no:04d}.{part_idx:02d}"
            chunk_records.append(
                {
                    "chunk_id": cid,
                    "kind": "source_page_window",
                    "source": "阿娇版+缠论.pdf",
                    "path": "kb/sources/normalized/pages.jsonl",
                    "title": (
                        f"p{page_no}"
                        + (f" lesson {lesson['lesson']}: {lesson['title']}" if lesson else "")
                    ),
                    "page_start": page_no,
                    "page_end": page_no,
                    "lesson": lesson["lesson"] if lesson else None,
                    "lesson_title": lesson["title"] if lesson else None,
                    "char_start": start,
                    "char_end": end,
                    "concepts": concepts_from_text(part, concepts),
                    "keywords": tokenize(part)[:80],
                    "text": part,
                }
            )
    return page_records, chunk_records


def split_markdown_sections(path: Path) -> list[tuple[str, int, int, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    sections: list[tuple[str, int, int, str]] = []
    starts: list[tuple[int, str]] = []
    for idx, line in enumerate(lines, start=1):
        match = re.match(r"^(#{1,3})\s+(.+?)\s*$", line)
        if match:
            starts.append((idx, match.group(2).strip()))
    if not starts:
        return [(path.stem, 1, len(lines), "\n".join(lines).strip())]
    for pos, (start, heading) in enumerate(starts):
        end = starts[pos + 1][0] - 1 if pos + 1 < len(starts) else len(lines)
        text = "\n".join(lines[start - 1 : end]).strip()
        if text:
            sections.append((heading, start, end, text))
    return sections


def chunk_fast_docs(concepts: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for file_name in FAST_FILES:
        path = CHANLUN_ROOT / file_name
        if not path.exists():
            continue
        for idx, (heading, line_start, line_end, text) in enumerate(split_markdown_sections(path), start=1):
            cid = f"fast.{path.stem}.{idx:02d}.{slug(heading)}"
            records.append(
                {
                    "chunk_id": cid,
                    "kind": "fast_markdown_section",
                    "source": "agent-stock chanlun fast package",
                    "path": rel(path),
                    "title": heading,
                    "line_start": line_start,
                    "line_end": line_end,
                    "concepts": concepts_from_text(text, concepts),
                    "keywords": tokenize(heading + "\n" + text)[:80],
                    "text": text,
                }
            )
    return records


def parse_svg(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise SystemExit(f"SVG parse error in {path}: {exc}") from exc
    ns = "{http://www.w3.org/2000/svg}"
    title = ""
    desc = ""
    title_el = root.find(f"{ns}title")
    if title_el is None:
        title_el = root.find("title")
    desc_el = root.find(f"{ns}desc")
    if desc_el is None:
        desc_el = root.find("desc")
    if title_el is not None and title_el.text:
        title = compact(title_el.text)
    if desc_el is not None and desc_el.text:
        desc = compact(desc_el.text)
    labels = []
    for item in root.iter():
        if item.tag.endswith("text") and item.text and item.text.strip():
            labels.append(compact(item.text))
    return {
        "id": path.stem,
        "file": rel(path),
        "title": title,
        "desc": desc,
        "viewBox": root.attrib.get("viewBox"),
        "width": root.attrib.get("width"),
        "height": root.attrib.get("height"),
        "text_labels": labels,
        "use_boundary": VISUAL_BOUNDARY,
        "sha256": sha256_file(path),
        "size": path.stat().st_size,
    }


def build_visual_index(index_data: dict[str, Any]) -> dict[str, Any]:
    cards = []
    card_by_file = {}
    for path in sorted((CHANLUN_ROOT / "figures").glob("*.svg")):
        card = parse_svg(path)
        cards.append(card)
        card_by_file[path.name] = card["id"]

    visual_cards = index_data.get("visual_cards") or {}
    for card in cards:
        meta = visual_cards.get(card["id"], {})
        card["use_for"] = meta.get("use_for")
        card["do_not_use_for"] = meta.get("do_not_use_for")
        related = []
        related_keywords = []
        for cid, concept in (index_data.get("concepts") or {}).items():
            fig = concept.get("figure")
            if fig and Path(fig).name == Path(card["file"]).name:
                related.append(cid)
                related_keywords.extend(str(keyword) for keyword in concept.get("keywords", []))
        card["related_concepts"] = related
        card["related_keywords"] = sorted(set(related_keywords))

    return {
        "schema_version": "1.0",
        "built_at": now_iso(),
        "visual_use_boundary": VISUAL_BOUNDARY,
        "cards": cards,
    }


def build_graph(concepts: dict[str, Any], chunks: list[dict[str, Any]], visual: dict[str, Any]) -> dict[str, Any]:
    nodes = []
    edges = []
    for cid, info in concepts.items():
        nodes.append({"id": f"concept:{cid}", "type": "concept", "label": cid, "keywords": info.get("keywords", [])})
        for page in info.get("source_pages", []):
            page_id = f"source_page:{page}"
            nodes.append({"id": page_id, "type": "source_page", "label": f"p{page}"})
            edges.append({"from": f"concept:{cid}", "to": page_id, "type": "anchored_to"})
        fig = info.get("figure")
        if fig:
            card_id = f"visual:{Path(fig).stem}"
            edges.append({"from": f"concept:{cid}", "to": card_id, "type": "uses_figure"})

    for chunk in chunks:
        chunk_node = {"id": f"chunk:{chunk['chunk_id']}", "type": "chunk", "label": chunk.get("title", "")}
        nodes.append(chunk_node)
        for cid in chunk.get("concepts", []):
            edges.append({"from": f"chunk:{chunk['chunk_id']}", "to": f"concept:{cid}", "type": "mentions"})
        page = chunk.get("page_start")
        if page:
            edges.append({"from": f"chunk:{chunk['chunk_id']}", "to": f"source_page:{page}", "type": "from_page"})

    for card in visual.get("cards", []):
        nodes.append({"id": f"visual:{card['id']}", "type": "visual_card", "label": card.get("title") or card["id"]})
        for cid in card.get("related_concepts", []):
            edges.append({"from": f"visual:{card['id']}", "to": f"concept:{cid}", "type": "illustrates"})

    unique_nodes = {}
    for node in nodes:
        unique_nodes[node["id"]] = node
    unique_edges = []
    seen_edges = set()
    for edge in edges:
        key = (edge.get("from"), edge.get("to"), edge.get("type"))
        if key in seen_edges:
            continue
        seen_edges.add(key)
        unique_edges.append(edge)
    return {"schema_version": "1.0", "built_at": now_iso(), "nodes": list(unique_nodes.values()), "edges": unique_edges}


def collect_assets(paths: list[Path]) -> list[dict[str, Any]]:
    assets = []
    seen = set()
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        r = rel(path)
        if r in seen:
            continue
        seen.add(r)
        suffix = path.suffix.lower().lstrip(".") or "file"
        role = "visual_card" if suffix == "svg" else "reference"
        if "kb/generated" in r:
            role = "generated_index"
        if "kb/sources" in r:
            role = "normalized_source"
        assets.append(
            {
                "path": r,
                "type": suffix,
                "role": role,
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
            }
        )
    return sorted(assets, key=lambda item: item["path"])


def concept_manifest(concepts: dict[str, Any], chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for cid, info in concepts.items():
        matched_chunks = [chunk["chunk_id"] for chunk in chunks if cid in chunk.get("concepts", [])]
        listed_chunks = matched_chunks[:CONCEPT_CHUNK_LIMIT]
        figure = info.get("figure")
        result.append(
            {
                "id": cid,
                "name": cid,
                "keywords": info.get("keywords", []),
                "source_pages": info.get("source_pages", []),
                "chunks": listed_chunks,
                "chunk_count": len(matched_chunks),
                "chunks_truncated": len(matched_chunks) > len(listed_chunks),
                "rule_ids": [chunk_id for chunk_id in matched_chunks if chunk_id.startswith("fast.rules.")],
                "svg_card": rel(CHANLUN_ROOT / figure) if figure else None,
                "visual_boundary": VISUAL_BOUNDARY,
                "output_contract": {field: "required" for field in OUTPUT_FIELDS},
            }
        )
    return result


def build_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Agent Stock Chanlun KB Manifest",
        "type": "object",
        "required": ["schema_version", "package", "assets", "concepts", "indexes", "output_contract"],
        "properties": {
            "schema_version": {"type": "string"},
            "package": {"type": "object"},
            "assets": {"type": "array"},
            "concepts": {"type": "array"},
            "indexes": {"type": "object"},
            "output_contract": {"type": "object"},
        },
    }


def build(args: argparse.Namespace) -> dict[str, Any]:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    NORMALIZED_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    source_text_path = Path(args.source_text).expanduser().resolve()
    if not source_text_path.exists():
        raise SystemExit(f"source text not found: {source_text_path}")

    index_data = load_json(CHANLUN_ROOT / "index.json", {})
    concepts = index_data.get("concepts") or {}
    toc = load_toc(Path(args.toc_json).expanduser().resolve() if args.toc_json else None)

    page_records, source_chunks = chunk_source_text(source_text_path, toc, concepts)
    pageindex_node_records: list[dict[str, Any]] = []
    pageindex_structure_copy: Path | None = None
    if args.pageindex_structure:
        pageindex_path = Path(args.pageindex_structure).expanduser().resolve()
        if not pageindex_path.exists():
            raise SystemExit(f"PageIndex structure not found: {pageindex_path}")
        pageindex_node_records, source_chunks, pageindex_structure_copy = chunk_pageindex_structure(
            pageindex_path,
            concepts,
        )
    fast_chunks = chunk_fast_docs(concepts)
    chunks = fast_chunks + source_chunks

    visual = build_visual_index(index_data)
    graph = build_graph(concepts, chunks, visual)

    pages_path = NORMALIZED_DIR / "pages.jsonl"
    fulltext_path = GENERATED_DIR / "chanlun.fulltext.jsonl"
    visual_path = GENERATED_DIR / "chanlun.visual.json"
    graph_path = GENERATED_DIR / "chanlun.graph.json"
    manifest_path = KB_ROOT / "manifest.json"
    schema_path = KB_ROOT / "manifest.schema.json"
    source_manifest_path = SOURCES_DIR / "source_manifest.json"
    pageindex_nodes_path = PAGEINDEX_DIR / "nodes.jsonl"

    write_jsonl(pages_path, page_records)
    if pageindex_node_records:
        write_jsonl(pageindex_nodes_path, pageindex_node_records)
    write_jsonl(fulltext_path, chunks)
    write_json(visual_path, visual)
    write_json(graph_path, graph)
    write_json(schema_path, build_schema())

    source_manifest = {
        "schema_version": "1.0",
        "source_id": "ajiao_chanlun_pdf_text",
        "title": "阿娇版+缠论.pdf extracted UTF-8 text",
        "built_at": now_iso(),
        "source_text_sha256": sha256_file(source_text_path),
        "page_count": len(page_records),
        "chunk_count": len(source_chunks),
        "pageindex_structure": rel(pageindex_structure_copy) if pageindex_structure_copy else None,
        "pageindex_node_count": len(pageindex_node_records),
        "runtime_note": "The generated KB does not require the source PDF or this source text path at runtime.",
    }
    write_json(source_manifest_path, source_manifest)

    asset_paths = [
        *(CHANLUN_ROOT / name for name in FAST_FILES),
        *(CHANLUN_ROOT / "figures").glob("*.svg"),
        *(KB_ROOT / "evals").glob("*.jsonl"),
        *(KB_ROOT / "generated" / "archive").glob("*"),
        *(PAGEINDEX_DIR).glob("*"),
        pages_path,
        fulltext_path,
        visual_path,
        graph_path,
        source_manifest_path,
        schema_path,
        KB_ROOT / "README.md",
    ]
    manifest = {
        "schema_version": "1.0",
        "package": {
            "name": "agent-stock-chanlun-kb",
            "version": "0.2",
            "base_path": "references/chanlun/kb",
            "built_at": now_iso(),
            "runtime_dependencies": ["Python 3 stdlib"],
            "optional_dependencies": ["embedding index, if generated separately"],
            "not_required_at_runtime": ["external RAG runtime", "Qdrant", "source PDF", "Downloads path"],
        },
        "assets": collect_assets(asset_paths),
        "documents": [
            {
                "id": "ajiao_chanlun_pdf_text",
                "title": "阿娇版+缠论.pdf extracted text",
                "normalized_path": rel(pages_path),
                "page_count": len(page_records),
                "chunk_count": len(source_chunks),
                "indexing": "pageindex_semantic_nodes" if pageindex_node_records else "fixed_page_windows",
            },
            {
                "id": "ajiao_chanlun_pageindex",
                "title": "阿娇版+缠论.pdf PageIndex text tree",
                "structure_path": rel(pageindex_structure_copy) if pageindex_structure_copy else None,
                "normalized_nodes_path": rel(pageindex_nodes_path) if pageindex_node_records else None,
                "node_count": len(pageindex_node_records),
                "active_fulltext": bool(pageindex_node_records),
            },
            {
                "id": "agent_stock_chanlun_fast",
                "title": "Agent Stock Chanlun fast package",
                "chunk_count": len(fast_chunks),
            },
        ],
        "concepts": concept_manifest(concepts, chunks),
        "indexes": {
            "fulltext_jsonl": rel(fulltext_path),
            "visual_json": rel(visual_path),
            "graph_json": rel(graph_path),
            "pageindex_nodes_jsonl": rel(pageindex_nodes_path) if pageindex_node_records else None,
            "embedding_jsonl_optional": "references/chanlun/kb/generated/chanlun.embeddings.jsonl",
        },
        "output_contract": {
            "required_fields": OUTPUT_FIELDS,
            "optional_fields": ["来源锚点"],
            "confidence_values": ["高", "中", "低", "未触发"],
            "low_confidence_rule": "If OHLC/history/timeframe evidence is insufficient, state 缠论结构置信度受限 and avoid aggressive action.",
        },
        "validation": {
            "schema": rel(schema_path),
            "commands": [
                "python3 scripts/chanlun_kb_validate.py",
                "python3 scripts/chanlun_kb_search.py search 中枢 --top-k 3",
            ],
        },
    }
    write_json(manifest_path, manifest)

    report = [
        "# Chanlun KB Build Report",
        "",
        f"- Built at: {manifest['package']['built_at']}",
        f"- Source pages: {len(page_records)}",
        f"- Source chunks: {len(source_chunks)}",
        f"- PageIndex nodes: {len(pageindex_node_records)}",
        f"- Fast chunks: {len(fast_chunks)}",
        f"- Visual cards: {len(visual.get('cards', []))}",
        f"- Graph nodes: {len(graph.get('nodes', []))}",
        f"- Graph edges: {len(graph.get('edges', []))}",
        "",
        "Generated files:",
        f"- `{rel(manifest_path)}`",
        f"- `{rel(fulltext_path)}`",
        f"- `{rel(visual_path)}`",
        f"- `{rel(graph_path)}`",
        f"- `{rel(pages_path)}`",
    ]
    if pageindex_structure_copy:
        report.extend(
            [
                f"- `{rel(pageindex_structure_copy)}`",
                f"- `{rel(pageindex_nodes_path)}`",
            ]
        )
    report_path = REPORTS_DIR / "chanlun_build_report.md"
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")

    return {
        "manifest": rel(manifest_path),
        "fulltext_records": len(chunks),
        "source_pages": len(page_records),
        "visual_cards": len(visual.get("cards", [])),
        "graph_nodes": len(graph.get("nodes", [])),
        "report": rel(report_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the agent-stock Chanlun KB indexes.")
    parser.add_argument("--source-text", required=True, help="Extracted UTF-8 text from 阿娇版+缠论.pdf")
    parser.add_argument("--toc-json", help="Optional toc_lessons.json with lesson/page anchors")
    parser.add_argument("--pageindex-structure", help="Optional PageIndex _structure.json to use as the active text index")
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary")
    args = parser.parse_args()

    result = build(args)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("Chanlun KB build complete")
        for key, value in result.items():
            print(f"- {key}: {value}")


if __name__ == "__main__":
    main()
