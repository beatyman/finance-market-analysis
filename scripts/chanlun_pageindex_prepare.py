#!/usr/bin/env python3
"""Prepare PageIndex-friendly text artifacts from the Ajiao Chanlun PDF.

The AgentStock runtime remains portable and stdlib-only. This script is a
build-time helper: it extracts page text, derives lesson anchors, and writes a
Markdown document whose headings can be indexed by PageIndex's Markdown mode.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
KB_ROOT = SKILL_ROOT / "references" / "chanlun" / "kb"
PAGEINDEX_DIR = KB_ROOT / "sources" / "pageindex"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def extract_pdf_text(pdf_path: Path, output_path: Path) -> None:
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        raise SystemExit("pdftotext not found; install poppler-utils or provide --source-text")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [pdftotext, "-layout", str(pdf_path), str(output_path)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def split_pages(source_text: str) -> list[dict[str, Any]]:
    pages = []
    for idx, raw in enumerate(source_text.split("\f"), start=1):
        text = raw.strip()
        if text:
            pages.append({"page": idx, "text": text})
    return pages


def compact_title(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[.。·…\s]+$", "", text)
    return text.strip()


def parse_toc(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    toc_text = "\n".join(page["text"] for page in pages[:4])
    toc_text = re.sub(r"教你炒股票\s*(\d+)\s*：\s*", r"\n教你炒股票 \1：", toc_text)
    toc_text = re.sub(r"\s*\n\s*", "\n", toc_text)
    pattern = re.compile(
        r"^教你炒股票\s*(?P<lesson>\d{1,3})\s*[：:]\s*"
        r"(?P<title>.*?)(?:\(\s*(?P<date>\d{4}-\d{2}-\d{2}[^)]*)\))"
        r"\s*[.。·…\s]*(?P<page>\d{1,4})\s*$",
        re.MULTILINE,
    )
    rows: dict[int, dict[str, Any]] = {}
    for match in pattern.finditer(toc_text):
        lesson = int(match.group("lesson"))
        if not (1 <= lesson <= 108):
            continue
        rows[lesson] = {
            "lesson": lesson,
            "title": compact_title(match.group("title")),
            "date": compact_title(match.group("date") or ""),
            "toc_page": int(match.group("page")),
        }
    return [rows[key] for key in sorted(rows)]


def fallback_toc_from_headings(pages: list[dict[str, Any]], existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = {int(row["lesson"]): row for row in existing}
    source = build_marked_source(pages)
    pattern = re.compile(
        r"教你炒股票\s*(?P<lesson>\d{1,3})\s*[：:]?\s*"
        r"(?P<title>[\s\S]{0,180}?)(?:\(\s*(?P<date>\d{4}-\d{2}-\d{2}[^)]*)\))"
    )
    for match in pattern.finditer(source):
        lesson = int(match.group("lesson"))
        if not (1 <= lesson <= 108) or lesson in rows:
            continue
        page_matches = list(re.finditer(r"<!-- PDF_PAGE_START:(\d{4}) -->", source[: match.start()]))
        page = int(page_matches[-1].group(1)) if page_matches else 1
        if page <= 4:
            continue
        title = compact_title(match.group("title"))
        if not title:
            title = f"教你炒股票 {lesson}"
        rows[lesson] = {
            "lesson": lesson,
            "title": title,
            "date": compact_title(match.group("date") or ""),
            "toc_page": page,
        }
    return [rows[key] for key in sorted(rows)]


def lesson_from_page(page: int, toc: list[dict[str, Any]]) -> dict[str, Any] | None:
    current = None
    for row in toc:
        if page >= int(row["toc_page"]):
            current = row
        else:
            break
    return current


def build_markdown_from_toc_pages(pages: list[dict[str, Any]], toc: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    if len(toc) < 100:
        raise SystemExit(f"found only {len(toc)} toc lessons; expected close to 108")
    toc_by_lesson = {int(row["lesson"]): row for row in toc}
    marked_source = build_marked_source(pages)
    page_starts = [
        (match.start(), int(match.group(1)))
        for match in re.finditer(r"<!-- PDF_PAGE_START:(\d{4}) -->", marked_source)
    ]

    def page_at(offset: int) -> int | None:
        current = None
        for pos, page in page_starts:
            if pos > offset:
                break
            current = page
        return current

    def offset_for_page(page: int) -> int | None:
        for pos, page_no in page_starts:
            if page_no >= page:
                return pos
        return page_starts[-1][0] if page_starts else None

    def heading_offset(row: dict[str, Any], previous_offset: int) -> int:
        lesson_no = int(row["lesson"])
        toc_page = int(row["toc_page"])
        pattern = re.compile(rf"教你炒股票\s*{lesson_no}(?!\d)\s*[：:]?")
        candidates = []
        for match in pattern.finditer(marked_source):
            page = page_at(match.start())
            if page is None or page <= 4 or match.start() <= previous_offset:
                continue
            candidates.append((abs(page - toc_page), page, match.start()))
        near = [item for item in candidates if item[0] <= 12]
        if near:
            near.sort(key=lambda item: (item[0], item[2]))
            return near[0][2]
        page_offset = offset_for_page(toc_page)
        if page_offset is not None and page_offset > previous_offset:
            return page_offset
        if candidates:
            candidates.sort(key=lambda item: item[2])
            return candidates[0][2]
        return previous_offset

    lines = [
        "# 阿娇版 缠论 108 课",
        "",
        "<!-- generated_for: AgentStock Chanlun PageIndex KB -->",
        "<!-- source: 阿娇版+缠论.pdf -->",
        "<!-- segmentation: toc-page semantic lessons -->",
        "",
    ]
    lesson_offsets = []
    previous_offset = -1
    for lesson_no in sorted(toc_by_lesson):
        offset = heading_offset(toc_by_lesson[lesson_no], previous_offset)
        lesson_offsets.append((lesson_no, offset))
        previous_offset = max(previous_offset, offset)

    if lesson_offsets:
        front_text = marked_source[: lesson_offsets[0][1]].strip()
    else:
        front_text = marked_source.strip()
    if front_text:
        nums = page_numbers(front_text)
        page_start = min(nums) if nums else 1
        page_end = max(nums) if nums else page_start
        lines.append("## front-matter 目录与课前材料")
        lines.append(f"<!-- page_start:{page_start} page_end:{page_end} -->")
        lines.append("")
        lines.append(front_text)
        lines.append("")

    lesson_infos = []
    for idx, (lesson_no, start_offset) in enumerate(lesson_offsets):
        row = toc_by_lesson[lesson_no]
        end_offset = lesson_offsets[idx + 1][1] if idx + 1 < len(lesson_offsets) else len(marked_source)
        lesson_text = marked_source[start_offset:end_offset].strip()
        nums = page_numbers(lesson_text)
        page_start = min(nums) if nums else page_at(start_offset) or int(row["toc_page"])
        page_end = max(nums) if nums else page_start
        lesson_infos.append(
            {
                "lesson": lesson_no,
                "title": row["title"],
                "date": row.get("date", ""),
                "toc_page": int(row["toc_page"]),
                "page_start": page_start,
                "page_end": page_end,
            }
        )
        heading = f"lesson-{lesson_no:03d} 教你炒股票 {lesson_no}：{clean_heading(row['title'])}"
        lines.append(f"## {heading}")
        lines.append(f"<!-- lesson:{lesson_no} -->")
        lines.append(f"<!-- lesson_title:{clean_heading(row['title'])} -->")
        if row.get("date"):
            lines.append(f"<!-- lesson_date:{row['date']} -->")
        lines.append(f"<!-- page_start:{page_start} page_end:{page_end} toc_page:{int(row['toc_page'])} -->")
        lines.append("")
        lines.append(lesson_text)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n", {"lesson_count": len(lesson_infos), "lessons": lesson_infos}


def page_blob(page: dict[str, Any]) -> str:
    page_no = int(page["page"])
    return (
        f"\n\n<!-- PDF_PAGE_START:{page_no:04d} -->\n"
        f"<!-- source_page:{page_no} -->\n"
        f"{page['text']}\n"
        f"<!-- PDF_PAGE_END:{page_no:04d} -->\n"
    )


def build_marked_source(pages: list[dict[str, Any]]) -> str:
    return "".join(page_blob(page) for page in pages)


def find_lesson_starts(marked_source: str, toc: list[dict[str, Any]]) -> list[dict[str, Any]]:
    toc_by_lesson = {int(row["lesson"]): row for row in toc}
    pattern = re.compile(
        r"教你炒股票\s*(?P<lesson>\d{1,3})\s*[：:]?\s*"
        r"(?P<title>[\s\S]{0,220}?)(?:\(\s*(?P<date>\d{4}-\d{2}-\d{2}[^)]*)\))"
    )
    starts: dict[int, dict[str, Any]] = {}
    page_starts = [(m.start(), int(m.group(1))) for m in re.finditer(r"<!-- PDF_PAGE_START:(\d{4}) -->", marked_source)]

    def page_at(offset: int) -> int | None:
        current = None
        for pos, page in page_starts:
            if pos > offset:
                break
            current = page
        return current

    for match in pattern.finditer(marked_source):
        lesson = int(match.group("lesson"))
        if lesson not in toc_by_lesson or lesson in starts:
            continue
        page = page_at(match.start())
        toc_page = int(toc_by_lesson[lesson]["toc_page"])
        if page is not None and abs(page - toc_page) > 2:
            continue
        starts[lesson] = {
            "lesson": lesson,
            "offset": match.start(),
            "page": page or toc_page,
            "title": compact_title(match.group("title")) or toc_by_lesson[lesson]["title"],
            "date": compact_title(match.group("date") or toc_by_lesson[lesson].get("date", "")),
            "toc_page": toc_page,
        }
    return [starts[key] for key in sorted(starts)]


def page_numbers(text: str) -> list[int]:
    return [int(item) for item in re.findall(r"<!-- PDF_PAGE_START:(\d{4}) -->", text)]


def clean_heading(text: str) -> str:
    text = re.sub(r"[#`<>]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def write_page_chunks(lines: list[str], text: str) -> None:
    pattern = re.compile(
        r"<!-- PDF_PAGE_START:(?P<page>\d{4}) -->[\s\S]*?<!-- PDF_PAGE_END:(?P=page) -->"
    )
    pos = 0
    segment_idx = 1
    for match in pattern.finditer(text):
        prefix = text[pos : match.start()].strip()
        if prefix:
            lines.append(f"### Segment {segment_idx:03d}")
            lines.append(prefix)
            lines.append("")
            segment_idx += 1
        page_no = int(match.group("page"))
        lines.append(f"### PDF page {page_no:04d}")
        lines.append(match.group(0).strip())
        lines.append("")
        pos = match.end()
    suffix = text[pos:].strip()
    if suffix:
        lines.append(f"### Segment {segment_idx:03d}")
        lines.append(suffix)
        lines.append("")


def build_pageindex_markdown(marked_source: str, toc: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    starts = find_lesson_starts(marked_source, toc)
    if len(starts) < 100:
        raise SystemExit(f"found only {len(starts)} lesson starts; expected close to 108")

    lines = [
        "# 阿娇版 缠论 108 课",
        "",
        "<!-- generated_for: AgentStock Chanlun PageIndex KB -->",
        "<!-- source: 阿娇版+缠论.pdf -->",
        "",
    ]

    front_text = marked_source[: starts[0]["offset"]].strip()
    if front_text:
        nums = page_numbers(front_text)
        lines.append("## front-matter 目录与课前材料")
        lines.append(f"<!-- page_start:{min(nums) if nums else 1} page_end:{max(nums) if nums else starts[0]['page']} -->")
        lines.append("")
        write_page_chunks(lines, front_text)

    lesson_infos = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1]["offset"] if idx + 1 < len(starts) else len(marked_source)
        body = marked_source[start["offset"] : end].strip()
        nums = page_numbers(body)
        page_start = min(nums) if nums else start["page"]
        page_end = max(nums) if nums else start["page"]
        lesson_infos.append(
            {
                "lesson": start["lesson"],
                "title": start["title"],
                "date": start["date"],
                "toc_page": start["toc_page"],
                "page_start": page_start,
                "page_end": page_end,
            }
        )
        heading = f"lesson-{start['lesson']:03d} 教你炒股票 {start['lesson']}：{clean_heading(start['title'])}"
        lines.append(f"## {heading}")
        lines.append(f"<!-- lesson:{start['lesson']} -->")
        lines.append(f"<!-- lesson_title:{clean_heading(start['title'])} -->")
        if start["date"]:
            lines.append(f"<!-- lesson_date:{start['date']} -->")
        lines.append(f"<!-- page_start:{page_start} page_end:{page_end} toc_page:{start['toc_page']} -->")
        lines.append("")
        write_page_chunks(lines, body)

    metadata = {
        "lesson_count": len(lesson_infos),
        "lessons": lesson_infos,
    }
    return "\n".join(lines).rstrip() + "\n", metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare PageIndex Markdown from 阿娇版+缠论.pdf")
    parser.add_argument("--pdf", required=True, help="Path to 阿娇版+缠论.pdf")
    parser.add_argument("--source-text", help="Existing pdftotext-style UTF-8 text with form-feed page breaks")
    parser.add_argument("--out-dir", default=str(PAGEINDEX_DIR), help="Output directory")
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary")
    args = parser.parse_args()

    pdf_path = Path(args.pdf).expanduser().resolve()
    if not pdf_path.exists():
        raise SystemExit(f"PDF not found: {pdf_path}")

    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    text_path = out_dir / "ajiao_chanlun_extracted.txt"
    md_path = out_dir / "ajiao_chanlun_pageindex.md"
    toc_path = out_dir / "toc_lessons.json"
    manifest_path = out_dir / "prepare_manifest.json"

    if args.source_text:
        provided = Path(args.source_text).expanduser().resolve()
        if not provided.exists():
            raise SystemExit(f"source text not found: {provided}")
        text_path.write_text(provided.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
    else:
        extract_pdf_text(pdf_path, text_path)

    source_text = text_path.read_text(encoding="utf-8", errors="ignore")
    pages = split_pages(source_text)
    toc = fallback_toc_from_headings(pages, parse_toc(pages))
    markdown, metadata = build_markdown_from_toc_pages(pages, toc)

    md_path.write_text(markdown, encoding="utf-8")
    write_json(toc_path, metadata["lessons"])
    manifest = {
        "schema_version": "1.0",
        "built_at": now_iso(),
        "pdf_path": str(pdf_path),
        "pdf_sha256": sha256_file(pdf_path),
        "source_text_path": text_path.name,
        "source_text_sha256": sha256_file(text_path),
        "pageindex_markdown_path": md_path.name,
        "pageindex_markdown_sha256": sha256_file(md_path),
        "toc_path": toc_path.name,
        "page_count": len(pages),
        "lesson_count": metadata["lesson_count"],
        "runtime_note": "Build-time PageIndex preparation only; AgentStock runtime does not require the PDF or PageIndex.",
    }
    write_json(manifest_path, manifest)

    result = {
        "source_text": str(text_path),
        "pageindex_markdown": str(md_path),
        "toc_json": str(toc_path),
        "manifest": str(manifest_path),
        "page_count": len(pages),
        "lesson_count": metadata["lesson_count"],
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("PageIndex preparation complete")
        for key, value in result.items():
            print(f"- {key}: {value}")


if __name__ == "__main__":
    main()
