#!/usr/bin/env python3
"""Validate Chanlun KB: manifest, generated indexes, and SVG cards.

Exit codes:
  0  all checks pass
  1  validation failure (content errors)
  2  generated indexes missing or stale — rebuild required
"""
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

# Skill root is the directory one level above this script directory.
SKILL_ROOT = Path(__file__).resolve().parent.parent
KB_ROOT = SKILL_ROOT / "references" / "chanlun" / "kb"

MANIFEST_PATH = KB_ROOT / "manifest.json"
FULLTEXT_PATH = KB_ROOT / "generated" / "chanlun.fulltext.jsonl"
VISUAL_PATH   = KB_ROOT / "generated" / "chanlun.visual.json"
GRAPH_PATH    = KB_ROOT / "generated" / "chanlun.graph.json"

OUTPUT_CONTRACT_FIELDS = [
    "操作级别", "走势定位", "买卖点", "结构依据",
    "图形参照", "置信度", "失效条件",
]

_errors: list[str] = []
_stale: list[str] = []
_warnings: list[str] = []


def _err(msg: str) -> None:
    _errors.append(msg)


def _stale_err(msg: str) -> None:
    _stale.append(msg)


def _warn(msg: str) -> None:
    _warnings.append(msg)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _check_asset(raw: str, context: str) -> "Path | None":
    """Verify path is relative and resolves to an existing file."""
    if os.path.isabs(raw):
        _err(f"{context}: asset path must be relative, got absolute: {raw!r}")
        return None
    resolved = SKILL_ROOT / raw
    if not resolved.exists():
        _err(f"{context}: asset file not found: {raw!r}")
        return None
    return resolved


def _check_integrity(
    path: Path, sha: "str | None", size: "int | None", context: str
) -> None:
    if size is not None:
        actual = path.stat().st_size
        if actual != size:
            _err(f"{context}: size mismatch (expected {size}, actual {actual})")
    if sha is not None:
        actual = _sha256(path)
        if actual != sha:
            _err(f"{context}: sha256 mismatch")


# ---------------------------------------------------------------------------
# Generated-index checks
# ---------------------------------------------------------------------------

def _validate_generated() -> None:
    specs = [
        ("fulltext JSONL", FULLTEXT_PATH, "jsonl"),
        ("visual JSON",    VISUAL_PATH,   "json"),
        ("graph JSON",     GRAPH_PATH,    "json"),
    ]
    for label, path, fmt in specs:
        if not path.exists():
            _stale_err(f"{label} missing — run build: {path.name}")
            continue
        if fmt == "jsonl":
            _check_jsonl(path, label)
        else:
            _check_json_file(path, label)


def _check_jsonl(path: Path, label: str) -> None:
    try:
        with open(path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if line:
                    try:
                        json.loads(line)
                    except json.JSONDecodeError as exc:
                        _err(f"{label} line {lineno}: {exc}")
                        return
    except OSError as exc:
        _err(f"Cannot read {label}: {exc}")


def _check_json_file(path: Path, label: str) -> None:
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        _err(f"{label} invalid: {exc}")


# ---------------------------------------------------------------------------
# Manifest checks
# ---------------------------------------------------------------------------

def _load_manifest() -> "dict | None":
    if not MANIFEST_PATH.exists():
        _err(f"Manifest not found: {MANIFEST_PATH}")
        return None
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _err(f"Manifest JSON parse error: {exc}")
        return None


def _validate_top_assets(manifest: dict) -> None:
    assets = manifest.get("assets")
    if isinstance(assets, list):
        for idx, asset in enumerate(assets):
            if not isinstance(asset, dict):
                _err(f"manifest.assets[{idx}]: expected object")
                continue
            raw = asset.get("path")
            if not isinstance(raw, str):
                _err(f"manifest.assets[{idx}]: missing relative path")
                continue
            path = _check_asset(raw, f"manifest.assets[{idx}]")
            if path:
                _check_integrity(path, asset.get("sha256"), asset.get("size"), f"manifest.assets[{idx}]")
        return
    if not isinstance(assets, dict):
        _err("manifest.assets: expected array or object")
        return
    for key, raw in assets.items():
        if not isinstance(raw, str):
            continue
        path = _check_asset(raw, f"manifest.assets.{key}")
        if path:
            _check_integrity(
                path,
                manifest.get(f"{key}_sha256"),
                manifest.get(f"{key}_size"),
                f"manifest.assets.{key}",
            )


def _validate_concepts(manifest: dict) -> None:
    concepts: list = manifest.get("concepts") or manifest.get("cards") or []
    asset_index = {}
    for asset in manifest.get("assets") or []:
        if isinstance(asset, dict) and isinstance(asset.get("path"), str):
            asset_index[asset["path"]] = asset
    if not concepts:
        _warn("Manifest has no concepts or cards array")
        return

    for concept in concepts:
        cid = concept.get("id") or concept.get("name") or "?"
        ctx = f"concept {cid!r}"

        # source_pages required
        if not concept.get("source_pages"):
            _err(f"{ctx}: missing or empty source_pages")

        # at least one chunk or rule reference
        has_ref = any(
            concept.get(k)
            for k in ("chunks", "rules", "chunk_ids", "rule_ids")
        )
        if not has_ref:
            _err(f"{ctx}: no chunk or rule reference (expected chunks, rules, chunk_ids, or rule_ids)")

        # output_contract with all required fields
        contract = concept.get("output_contract")
        if contract is None:
            _err(f"{ctx}: missing output_contract")
        else:
            for field in OUTPUT_CONTRACT_FIELDS:
                if field not in contract:
                    _err(f"{ctx}: output_contract missing field {field!r}")

        # SVG card validation
        svg_raw = concept.get("svg_card") or concept.get("svg")
        if svg_raw:
            svg_path = _check_asset(svg_raw, f"{ctx} svg_card")
            if svg_path:
                asset = asset_index.get(svg_raw)
                if asset:
                    _check_integrity(svg_path, asset.get("sha256"), asset.get("size"), f"{ctx} svg_card")
                _validate_svg(svg_path, concept, ctx)


def _validate_svg(path: Path, concept: dict, ctx: str) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        _err(f"{ctx}: cannot read SVG: {exc}")
        return

    if not re.search(r"<title[\s/>]", text):
        _err(f"{ctx}: SVG missing <title> element")
    if not re.search(r"<desc[\s/>]", text):
        _err(f"{ctx}: SVG missing <desc> element")

    desc_match = re.search(r"<desc[^>]*>([\s\S]*?)</desc>", text)
    desc_text = desc_match.group(1) if desc_match else ""
    visual_boundary = str(concept.get("visual_boundary") or "")

    combined = (desc_text + visual_boundary).lower()
    if "qualitative" not in combined:
        _err(
            f"{ctx}: qualitative-boundary phrase absent from SVG <desc> "
            f"and manifest visual_boundary"
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Chanlun KB artifacts")
    parser.add_argument(
        "--json", action="store_true", help="Machine-readable JSON summary on stdout"
    )
    args = parser.parse_args()

    _validate_generated()
    manifest = _load_manifest()
    if manifest is not None:
        _validate_top_assets(manifest)
        _validate_concepts(manifest)

    has_stale = bool(_stale)
    has_errors = bool(_errors)

    if has_stale:
        exit_code = 2
    elif has_errors:
        exit_code = 1
    else:
        exit_code = 0

    if args.json:
        print(
            json.dumps(
                {
                    "passed": exit_code == 0,
                    "exit_code": exit_code,
                    "errors": _errors,
                    "stale_errors": _stale,
                    "warnings": _warnings,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        all_issues = _stale + _errors
        if exit_code == 0:
            print(f"OK  Chanlun KB valid  ({len(_warnings)} warning(s))")
        elif exit_code == 2:
            print(
                f"STALE  {len(_stale)} rebuild-required issue(s), "
                f"{len(_errors)} error(s), {len(_warnings)} warning(s)"
            )
        else:
            print(
                f"FAIL  {len(_errors)} error(s), {len(_warnings)} warning(s)"
            )
        for msg in _stale:
            print(f"  [STALE] {msg}")
        for msg in _errors:
            print(f"  [ERR]   {msg}")
        for msg in _warnings:
            print(f"  [WARN]  {msg}")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
