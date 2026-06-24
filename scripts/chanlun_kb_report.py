#!/usr/bin/env python3
"""Generate a Chanlun KB health report and write it under references/chanlun/kb/reports/.

Exit codes mirror chanlun_kb_validate.py:
  0  all checks pass
  1  validation failure (content errors)
  2  generated indexes missing or stale — rebuild required
"""
import argparse
import datetime
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
KB_ROOT = SKILL_ROOT / "references" / "chanlun" / "kb"
REPORTS_DIR = KB_ROOT / "reports"
REPORT_RETENTION = 5

MANIFEST_PATH = KB_ROOT / "manifest.json"
FULLTEXT_PATH = KB_ROOT / "generated" / "chanlun.fulltext.jsonl"
VISUAL_PATH   = KB_ROOT / "generated" / "chanlun.visual.json"
GRAPH_PATH    = KB_ROOT / "generated" / "chanlun.graph.json"

OUTPUT_CONTRACT_FIELDS = [
    "操作级别", "走势定位", "买卖点", "结构依据",
    "图形参照", "置信度", "失效条件",
]


# ---------------------------------------------------------------------------
# Run validation by importing the sibling module (subprocess fallback)
# ---------------------------------------------------------------------------

def _run_validation() -> dict:
    """Return the JSON result dict from chanlun_kb_validate, exit_code included."""
    validate_path = Path(__file__).resolve().parent / "chanlun_kb_validate.py"

    # Prefer direct import so we share the same process and avoid subprocess overhead.
    try:
        spec = importlib.util.spec_from_file_location("chanlun_kb_validate", validate_path)
        mod = importlib.util.module_from_spec(spec)
        # Reset module-level lists each time (they are global in the validator).
        spec.loader.exec_module(mod)
        mod._errors.clear()
        mod._stale.clear()
        mod._warnings.clear()

        mod._validate_generated()
        manifest = mod._load_manifest()
        if manifest is not None:
            mod._validate_top_assets(manifest)
            mod._validate_concepts(manifest)

        has_stale = bool(mod._stale)
        has_errors = bool(mod._errors)
        exit_code = 2 if has_stale else (1 if has_errors else 0)

        return {
            "passed": exit_code == 0,
            "exit_code": exit_code,
            "errors": list(mod._errors),
            "stale_errors": list(mod._stale),
            "warnings": list(mod._warnings),
        }
    except Exception:
        pass

    # Fallback: subprocess
    result = subprocess.run(
        [sys.executable, str(validate_path), "--json"],
        capture_output=True,
        text=True,
    )
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        data = {
            "passed": False,
            "exit_code": 1,
            "errors": [f"validate subprocess error: {result.stderr.strip()}"],
            "stale_errors": [],
            "warnings": [],
        }
    data.setdefault("exit_code", result.returncode)
    return data


# ---------------------------------------------------------------------------
# Coverage stats from generated indexes
# ---------------------------------------------------------------------------

def _coverage_stats() -> dict:
    stats: dict = {}

    # fulltext JSONL: count lines
    if FULLTEXT_PATH.exists():
        try:
            with open(FULLTEXT_PATH, encoding="utf-8") as fh:
                chunk_count = sum(1 for ln in fh if ln.strip())
            stats["fulltext_chunks"] = chunk_count
        except OSError:
            stats["fulltext_chunks"] = None
    else:
        stats["fulltext_chunks"] = None

    # visual JSON: count concept entries
    if VISUAL_PATH.exists():
        try:
            data = json.loads(VISUAL_PATH.read_text(encoding="utf-8"))
            # Support both list and dict-of-concepts layouts.
            if isinstance(data, list):
                stats["visual_concepts"] = len(data)
            elif isinstance(data, dict):
                cards = data.get("cards")
                stats["visual_concepts"] = len(cards) if isinstance(cards, list) else len(data)
            else:
                stats["visual_concepts"] = None
        except (json.JSONDecodeError, OSError):
            stats["visual_concepts"] = None
    else:
        stats["visual_concepts"] = None

    # graph JSON: count nodes/edges if present
    if GRAPH_PATH.exists():
        try:
            data = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                nodes = data.get("nodes") or data.get("vertices") or []
                edges = data.get("edges") or data.get("links") or []
                stats["graph_nodes"] = len(nodes) if isinstance(nodes, list) else None
                stats["graph_edges"] = len(edges) if isinstance(edges, list) else None
            else:
                stats["graph_nodes"] = None
                stats["graph_edges"] = None
        except (json.JSONDecodeError, OSError):
            stats["graph_nodes"] = None
            stats["graph_edges"] = None
    else:
        stats["graph_nodes"] = None
        stats["graph_edges"] = None

    # manifest: concept count, document count, asset count
    if MANIFEST_PATH.exists():
        try:
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            concepts = manifest.get("concepts") or manifest.get("cards") or []
            stats["concept_count"] = len(concepts)
            stats["document_count"] = len(manifest.get("documents") or [])
            stats["asset_count"] = len(manifest.get("assets") or [])
            # source page totals from documents
            page_totals = [
                d.get("page_count", 0)
                for d in (manifest.get("documents") or [])
                if isinstance(d.get("page_count"), int)
            ]
            stats["total_pages"] = sum(page_totals) if page_totals else None
        except (json.JSONDecodeError, OSError):
            stats["concept_count"] = None
    else:
        stats["concept_count"] = None

    return stats


# ---------------------------------------------------------------------------
# Contract analysis from manifest concepts
# ---------------------------------------------------------------------------

def _contract_analysis() -> dict:
    result: dict = {"concepts": [], "all_complete": True, "missing_fields": {}}
    if not MANIFEST_PATH.exists():
        result["all_complete"] = False
        return result

    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        result["all_complete"] = False
        return result

    concepts = manifest.get("concepts") or manifest.get("cards") or []
    for concept in concepts:
        cid = concept.get("id") or concept.get("name") or "?"
        contract = concept.get("output_contract") or {}
        missing = [f for f in OUTPUT_CONTRACT_FIELDS if f not in contract]
        entry = {"id": cid, "missing_fields": missing, "complete": not missing}
        result["concepts"].append(entry)
        if missing:
            result["all_complete"] = False
            result["missing_fields"][cid] = missing

    return result


# ---------------------------------------------------------------------------
# Boundary check: visual_boundary in all concepts
# ---------------------------------------------------------------------------

def _boundary_analysis() -> dict:
    result: dict = {"concepts": [], "all_have_boundary": True}
    if not MANIFEST_PATH.exists():
        result["all_have_boundary"] = False
        return result

    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        result["all_have_boundary"] = False
        return result

    concepts = manifest.get("concepts") or manifest.get("cards") or []
    for concept in concepts:
        cid = concept.get("id") or concept.get("name") or "?"
        boundary = concept.get("visual_boundary") or ""
        has_qualitative = "qualitative" in boundary.lower()
        entry = {
            "id": cid,
            "has_visual_boundary": bool(boundary),
            "has_qualitative_phrase": has_qualitative,
        }
        result["concepts"].append(entry)
        if not boundary or not has_qualitative:
            result["all_have_boundary"] = False

    return result


# ---------------------------------------------------------------------------
# Risk inference
# ---------------------------------------------------------------------------

def _infer_risks(validation: dict, coverage: dict, contract: dict, boundary: dict) -> list[str]:
    risks: list[str] = []

    if validation["exit_code"] == 2:
        risks.append("Generated indexes are missing or stale — KB searches will return no results until rebuilt.")

    if validation["errors"]:
        risks.append(f"{len(validation['errors'])} validation error(s) may cause incorrect KB lookups.")

    if validation["warnings"]:
        risks.append(f"{len(validation['warnings'])} warning(s) detected; review before production use.")

    chunks = coverage.get("fulltext_chunks")
    if chunks is None:
        risks.append("fulltext JSONL index absent — full-text search unavailable.")
    elif chunks < 100:
        risks.append(f"fulltext JSONL contains only {chunks} chunks — coverage may be insufficient.")

    if not contract["all_complete"]:
        n = len(contract["missing_fields"])
        risks.append(f"{n} concept(s) have incomplete output_contract — agent may produce malformed responses.")

    if not boundary["all_have_boundary"]:
        risks.append("One or more concepts lack a qualitative visual_boundary phrase — SVG misuse risk.")

    if not risks:
        risks.append("No significant risks detected.")

    return risks


def _next_actions(validation: dict, coverage: dict) -> list[str]:
    actions: list[str] = []

    if validation["exit_code"] == 2:
        actions.append("Run the KB build pipeline to regenerate fulltext/visual/graph indexes.")

    if validation["errors"]:
        actions.append("Run `python3 scripts/chanlun_kb_validate.py` and fix all [ERR] items.")

    if validation["warnings"]:
        actions.append("Review [WARN] items from validator output and address as appropriate.")

    chunks = coverage.get("fulltext_chunks")
    if chunks is not None and chunks < 100:
        actions.append("Expand source material or re-run chunking to increase KB coverage.")

    if not actions:
        actions.append("KB is healthy — no immediate actions required.")
        actions.append("Consider scheduling periodic re-validation (e.g. after source updates).")

    return actions


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def _status_label(exit_code: int) -> str:
    return {0: "PASS", 1: "FAIL", 2: "STALE"}.get(exit_code, "UNKNOWN")


def _render_markdown(
    ts: str,
    validation: dict,
    coverage: dict,
    contract: dict,
    boundary: dict,
    risks: list[str],
    actions: list[str],
) -> str:
    status = _status_label(validation["exit_code"])
    lines: list[str] = []

    lines += [
        f"# Chanlun KB Report — {ts}",
        "",
        f"**Status:** {status}  |  "
        f"Errors: {len(validation['errors'])}  |  "
        f"Stale: {len(validation['stale_errors'])}  |  "
        f"Warnings: {len(validation['warnings'])}",
        "",
    ]

    # Summary
    lines += ["## Summary", ""]
    if validation["passed"]:
        lines.append("All validation checks passed. KB is ready for use.")
    elif validation["exit_code"] == 2:
        lines.append(
            "One or more generated indexes are **missing or stale**. "
            "The KB requires a rebuild before it can be used reliably."
        )
    else:
        lines.append(
            f"Validation found **{len(validation['errors'])} error(s)**. "
            "Review the Contract and Risks sections below."
        )
    lines.append("")

    # Coverage
    lines += ["## Coverage", ""]
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Concepts in manifest | {coverage.get('concept_count', 'N/A')} |")
    lines.append(f"| Documents | {coverage.get('document_count', 'N/A')} |")
    lines.append(f"| Assets | {coverage.get('asset_count', 'N/A')} |")
    lines.append(f"| Source pages (total) | {coverage.get('total_pages', 'N/A')} |")
    lines.append(f"| Fulltext chunks | {coverage.get('fulltext_chunks', 'N/A')} |")
    lines.append(f"| Visual concepts (index) | {coverage.get('visual_concepts', 'N/A')} |")
    lines.append(f"| Graph nodes | {coverage.get('graph_nodes', 'N/A')} |")
    lines.append(f"| Graph edges | {coverage.get('graph_edges', 'N/A')} |")
    lines.append("")

    # Contract
    lines += ["## Contract", ""]
    if contract["all_complete"]:
        lines.append("All concepts have complete `output_contract` fields.")
    else:
        lines.append("The following concepts have **incomplete** output_contract:")
        lines.append("")
        for cid, missing in contract["missing_fields"].items():
            lines.append(f"- `{cid}`: missing {', '.join(f'`{f}`' for f in missing)}")
    lines.append("")

    # Boundary
    lines += ["## Boundary", ""]
    if boundary["all_have_boundary"]:
        lines.append("All concepts carry a qualitative `visual_boundary` phrase.")
    else:
        lines.append("Concept(s) missing qualitative visual_boundary:")
        lines.append("")
        for entry in boundary["concepts"]:
            if not entry["has_visual_boundary"] or not entry["has_qualitative_phrase"]:
                issue = "no boundary" if not entry["has_visual_boundary"] else "missing 'qualitative'"
                lines.append(f"- `{entry['id']}`: {issue}")
    lines.append("")

    # Validation detail
    if validation["stale_errors"] or validation["errors"] or validation["warnings"]:
        lines += ["### Validation Detail", ""]
        for msg in validation["stale_errors"]:
            lines.append(f"- **[STALE]** {msg}")
        for msg in validation["errors"]:
            lines.append(f"- **[ERR]** {msg}")
        for msg in validation["warnings"]:
            lines.append(f"- [WARN] {msg}")
        lines.append("")

    # Risks
    lines += ["## Risks", ""]
    for risk in risks:
        lines.append(f"- {risk}")
    lines.append("")

    # Next Actions
    lines += ["## Next Actions", ""]
    for action in actions:
        lines.append(f"1. {action}")
    lines.append("")

    return "\n".join(lines)


def _build_json_report(
    ts: str,
    validation: dict,
    coverage: dict,
    contract: dict,
    boundary: dict,
    risks: list[str],
    actions: list[str],
) -> dict:
    return {
        "generated_at": ts,
        "status": _status_label(validation["exit_code"]),
        "exit_code": validation["exit_code"],
        "summary": {
            "passed": validation["passed"],
            "error_count": len(validation["errors"]),
            "stale_count": len(validation["stale_errors"]),
            "warning_count": len(validation["warnings"]),
        },
        "coverage": coverage,
        "contract": contract,
        "boundary": boundary,
        "validation_detail": {
            "errors": validation["errors"],
            "stale_errors": validation["stale_errors"],
            "warnings": validation["warnings"],
        },
        "risks": risks,
        "next_actions": actions,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Chanlun KB health report")
    parser.add_argument(
        "--json", action="store_true",
        help="Also print machine-readable JSON summary to stdout",
    )
    args = parser.parse_args()

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    ts_iso = datetime.datetime.now().isoformat(timespec="seconds")

    validation = _run_validation()
    coverage = _coverage_stats()
    contract = _contract_analysis()
    boundary = _boundary_analysis()
    risks = _infer_risks(validation, coverage, contract, boundary)
    actions = _next_actions(validation, coverage)

    md_report = _render_markdown(ts_iso, validation, coverage, contract, boundary, risks, actions)
    json_report = _build_json_report(ts_iso, validation, coverage, contract, boundary, risks, actions)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    md_path = REPORTS_DIR / f"chanlun_validate_{ts}.md"
    json_path = REPORTS_DIR / f"chanlun_validate_{ts}.json"

    md_path.write_text(md_report, encoding="utf-8")
    json_path.write_text(
        json.dumps(json_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    old_reports = sorted(REPORTS_DIR.glob("chanlun_validate_*.md"), key=lambda path: path.stat().st_mtime, reverse=True)
    for obsolete in old_reports[REPORT_RETENTION:]:
        obsolete_json = obsolete.with_suffix(".json")
        try:
            obsolete.unlink()
        except OSError:
            pass
        if obsolete_json.exists():
            try:
                obsolete_json.unlink()
            except OSError:
                pass

    status_line = _status_label(validation["exit_code"])
    print(f"{status_line}  Report written:")
    print(f"  {md_path}")
    print(f"  {json_path}")

    if args.json:
        print(json.dumps(json_report, ensure_ascii=False, indent=2))

    sys.exit(validation["exit_code"])


if __name__ == "__main__":
    main()
