#!/usr/bin/env python3
"""Zero-dependency helpers for the Image-to-Knowledge Codex skill.

The script intentionally avoids mandatory third-party dependencies. If Pillow
is installed it is used for exact image cropping; otherwise macOS sips is used.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp", ".gif"}
SIPS = shutil.which("sips")

try:
    from PIL import Image, ImageEnhance, ImageFilter  # type: ignore
except Exception:  # pragma: no cover - depends on local optional package
    Image = None
    ImageEnhance = None
    ImageFilter = None


def now_run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def collect_images(inputs: Sequence[str]) -> List[Path]:
    files: List[Path] = []
    for item in inputs:
        path = Path(item).expanduser()
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in IMAGE_EXTENSIONS:
                    files.append(child.resolve())
        elif path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            files.append(path.resolve())
    return sorted(dict.fromkeys(files))


def read_image_meta(path: Path) -> Dict[str, Any]:
    if Image is not None:
        try:
            with Image.open(path) as img:
                return {
                    "width": int(img.width),
                    "height": int(img.height),
                    "format": str(img.format or path.suffix.lstrip(".").upper()),
                    "is_readable": True,
                    "read_error": None,
                }
        except Exception as exc:
            return {"width": None, "height": None, "format": None, "is_readable": False, "read_error": str(exc)}

    if not SIPS:
        return {"width": None, "height": None, "format": None, "is_readable": False, "read_error": "sips not found"}

    try:
        result = subprocess.run(
            [SIPS, "-g", "pixelWidth", "-g", "pixelHeight", "-g", "format", str(path)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        return {"width": None, "height": None, "format": None, "is_readable": False, "read_error": exc.stderr.strip()}

    data: Dict[str, Any] = {"width": None, "height": None, "format": None, "is_readable": True, "read_error": None}
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("pixelWidth:"):
            data["width"] = int(stripped.split(":", 1)[1].strip())
        elif stripped.startswith("pixelHeight:"):
            data["height"] = int(stripped.split(":", 1)[1].strip())
        elif stripped.startswith("format:"):
            data["format"] = stripped.split(":", 1)[1].strip()
    if data["width"] is None or data["height"] is None:
        data["is_readable"] = False
        data["read_error"] = "missing dimensions from sips output"
    return data


def enhance_reasons(width: Optional[int], height: Optional[int]) -> Tuple[bool, List[str]]:
    reasons = []
    if width is None or height is None:
        return False, reasons
    if width < 1200 or height < 800:
        reasons.append("T1: low resolution")
    return bool(reasons), reasons


def run_preflight(inputs: Sequence[str], output_dir: Path, run_id: Optional[str] = None) -> Dict[str, Any]:
    run_id = run_id or now_run_id()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    images = []

    for idx, image_path in enumerate(collect_images(inputs), 1):
        meta = read_image_meta(image_path)
        recommended, reasons = enhance_reasons(meta.get("width"), meta.get("height"))
        images.append(
            {
                "id": f"IMG-{idx:02d}",
                "path": str(image_path),
                "filename": image_path.name,
                "width": meta.get("width"),
                "height": meta.get("height"),
                "format": meta.get("format"),
                "file_size_kb": round(image_path.stat().st_size / 1024, 2),
                "is_readable": bool(meta.get("is_readable")),
                "read_error": meta.get("read_error"),
                "has_text": None,
                "recommended_enhance": recommended,
                "enhance_reasons": reasons,
            }
        )

    manifest = {"run_id": run_id, "created_at": datetime.now().isoformat(timespec="seconds"), "images": images}
    write_json(output_dir / f"{run_id}_manifest.json", manifest)
    write_manifest_markdown(output_dir / f"{run_id}_manifest.md", manifest)
    return manifest


def write_manifest_markdown(path: Path, manifest: Dict[str, Any]) -> None:
    lines = [
        f"# Image Manifest {manifest['run_id']}",
        "",
        "| 图片编号 | 文件名 | 尺寸 | 格式 | 可读 | 推荐增强 | 原因 |",
        "|---|---|---:|---|---|---|---|",
    ]
    for item in manifest["images"]:
        size = "-" if not item["width"] else f"{item['width']}x{item['height']}"
        reasons = ", ".join(item.get("enhance_reasons") or [])
        lines.append(
            f"| {item['id']} | {item['filename']} | {size} | {item.get('format') or '-'} | "
            f"{'yes' if item['is_readable'] else 'no'} | {'yes' if item['recommended_enhance'] else 'no'} | {reasons} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_scaffold(base_dir: Path, run_id: Optional[str] = None) -> Path:
    run_id = run_id or now_run_id()
    run_dir = Path(base_dir) / run_id
    for name in ["input", "work", "crops", "output"]:
        (run_dir / name).mkdir(parents=True, exist_ok=True)
    return run_dir


def pct_to_box(width: int, height: int, region: Dict[str, Any], overlap_pct: float) -> Tuple[int, int, int, int]:
    x1 = max(0, int(width * (float(region["x_start_pct"]) / 100.0 - overlap_pct)))
    x2 = min(width, int(width * (float(region["x_end_pct"]) / 100.0 + overlap_pct)))
    y1 = max(0, int(height * (float(region["y_start_pct"]) / 100.0 - overlap_pct)))
    y2 = min(height, int(height * (float(region["y_end_pct"]) / 100.0 + overlap_pct)))
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"invalid crop box for region {region!r}: {(x1, y1, x2, y2)}")
    return x1, y1, x2, y2


def slugify(value: str, fallback: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-").lower()
    return slug or fallback.lower()


def image_by_id(manifest: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {item["id"]: item for item in manifest.get("images", [])}


def crop_with_pillow(src: Path, dst: Path, box: Tuple[int, int, int, int], scale: int = 1) -> bool:
    if Image is None:
        return False
    try:
        with Image.open(src) as img:
            crop = img.crop(box)
            if scale > 1:
                crop = crop.resize((crop.width * scale, crop.height * scale), Image.Resampling.LANCZOS)
                if ImageFilter is not None:
                    crop = crop.filter(ImageFilter.SHARPEN)
                if ImageEnhance is not None:
                    crop = ImageEnhance.Contrast(crop).enhance(1.3)
            crop.save(dst)
        return True
    except Exception:
        return False


def crop_with_sips(src: Path, dst: Path, box: Tuple[int, int, int, int]) -> Tuple[bool, Optional[str]]:
    if not SIPS:
        return False, "sips not found"
    x1, y1, x2, y2 = box
    width = x2 - x1
    height = y2 - y1
    try:
        subprocess.run(
            [SIPS, "-c", str(height), str(width), "--cropOffset", str(y1), str(x1), str(src), "--out", str(dst)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        return True, None
    except subprocess.CalledProcessError as exc:
        return False, exc.stderr.strip() or exc.stdout.strip()


def save_crop(src: Path, dst: Path, box: Tuple[int, int, int, int], scale: int = 1) -> Tuple[str, Optional[str]]:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if crop_with_pillow(src, dst, box, scale=scale):
        return "pillow", None
    ok, error = crop_with_sips(src, dst, box)
    if ok:
        return "sips", None
    shutil.copy2(src, dst)
    return "copy-fallback", error or "crop failed; copied source image"


def run_crop(manifest_path: Path, regions_path: Path, output_dir: Path, overlap_pct: float = 0.05, scale: int = 1) -> Dict[str, Any]:
    manifest = read_json(Path(manifest_path))
    regions = read_json(Path(regions_path))
    by_id = image_by_id(manifest)
    output_dir = Path(output_dir)
    crops: List[Dict[str, Any]] = []

    for image_id, image_regions in regions.items():
        image = by_id.get(image_id)
        if not image or not image.get("is_readable"):
            continue
        src = Path(image["path"])
        for region in image_regions:
            box = pct_to_box(int(image["width"]), int(image["height"]), region, overlap_pct)
            region_id = str(region["region_id"])
            name_slug = slugify(str(region.get("name") or ""), region_id)
            out_path = output_dir / f"{image_id}_{region_id}_{name_slug}.png"
            method, warning = save_crop(src, out_path, box, scale=scale)
            crops.append(
                {
                    "image_id": image_id,
                    "region_id": region_id,
                    "name": region.get("name"),
                    "path": str(out_path),
                    "box_px": {"x_start": box[0], "y_start": box[1], "x_end": box[2], "y_end": box[3]},
                    "method": method,
                    "warning": warning,
                }
            )

    index = {"run_id": manifest.get("run_id"), "crops": crops}
    write_json(output_dir / "crops_index.json", index)
    return index


def run_grid(manifest_path: Path, output_dir: Path, rows: int = 2, cols: int = 2, overlap_pct: float = 0.05) -> Dict[str, Any]:
    if rows < 1 or cols < 1:
        raise ValueError("rows and cols must be >= 1")
    manifest = read_json(Path(manifest_path))
    output_dir = Path(output_dir)
    crops: List[Dict[str, Any]] = []

    for image in manifest.get("images", []):
        if not image.get("is_readable"):
            continue
        width = int(image["width"])
        height = int(image["height"])
        src = Path(image["path"])
        for row in range(rows):
            for col in range(cols):
                region_id = f"R{row + 1}C{col + 1}"
                region = {
                    "region_id": region_id,
                    "name": f"grid-{region_id}",
                    "x_start_pct": col * 100 / cols,
                    "x_end_pct": (col + 1) * 100 / cols,
                    "y_start_pct": row * 100 / rows,
                    "y_end_pct": (row + 1) * 100 / rows,
                }
                box = pct_to_box(width, height, region, overlap_pct)
                out_path = output_dir / f"{image['id']}_{region_id}_grid.png"
                method, warning = save_crop(src, out_path, box)
                crops.append(
                    {
                        "image_id": image["id"],
                        "region_id": region_id,
                        "name": region["name"],
                        "path": str(out_path),
                        "box_px": {"x_start": box[0], "y_start": box[1], "x_end": box[2], "y_end": box[3]},
                        "method": method,
                        "warning": warning,
                    }
                )

    index = {"run_id": manifest.get("run_id"), "grid": {"rows": rows, "cols": cols}, "crops": crops}
    write_json(output_dir / "crops_index.json", index)
    return index


RAW_LINE_RE = re.compile(r"^\s*[-*]\s*\[(?P<line>[A-Za-z0-9_-]+)\]\s*(?P<text>.+?)\s*$")
IMAGE_HEADING_RE = re.compile(r"IMG-\d{2,}")


def parse_raw_extraction(raw_text: str) -> Dict[Tuple[str, str], str]:
    current_image: Optional[str] = None
    lines: Dict[Tuple[str, str], str] = {}
    for raw_line in raw_text.splitlines():
        image_match = IMAGE_HEADING_RE.search(raw_line)
        if image_match:
            current_image = image_match.group(0)
        line_match = RAW_LINE_RE.match(raw_line)
        if current_image and line_match:
            line_id = line_match.group("line")
            lines[(current_image, line_id)] = line_match.group("text").strip()
    return lines


def knowledge_items_from_markdown(text: str) -> List[str]:
    items = []
    in_confirmation = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            in_confirmation = "待确认" in stripped or "confirmation" in stripped.lower()
            continue
        if in_confirmation:
            continue
        if stripped.startswith(("- ", "* ")) and not stripped.startswith(("- [", "* [")):
            item = stripped[2:].strip()
            if item:
                items.append(item)
            continue
        if re.match(r"^\d+[.)]\s+\S+", stripped):
            items.append(re.sub(r"^\d+[.)]\s+", "", stripped).strip())
            continue
        if stripped.startswith("|") and stripped.endswith("|") and "---" not in stripped:
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if cells and not any(cell in {"序号", "位置", "当前内容", "不确定原因"} for cell in cells):
                items.append(" | ".join(cells))
    return items


def count_uncertain(text: str) -> int:
    markers = ["识别不确定", "不确定", "待用户确认", "uncertain", "UNRESOLVED"]
    return sum(text.count(marker) for marker in markers)


def run_validate(
    manifest_path: Path,
    raw_path: Path,
    knowledge_path: Path,
    source_map_path: Path,
    output_dir: Path,
    uncertain_threshold: float = 0.2,
) -> Dict[str, Any]:
    manifest = read_json(Path(manifest_path))
    raw_text = Path(raw_path).read_text(encoding="utf-8")
    knowledge_text = Path(knowledge_path).read_text(encoding="utf-8")
    source_map = read_json(Path(source_map_path))
    raw_lines = parse_raw_extraction(raw_text)
    source_items = source_map.get("items", [])
    issues: List[str] = []
    warnings: List[str] = []

    if not source_items:
        issues.append("source_map has no items")

    contributed_images = set()
    for item in source_items:
        sources = item.get("sources") or []
        if not sources:
            issues.append(f"{item.get('knowledge_id', '<unknown>')} has no sources")
            continue
        for source in sources:
            image_id = source.get("image_id")
            line_id = source.get("line_id")
            if image_id:
                contributed_images.add(image_id)
            if not image_id or not line_id:
                issues.append(f"{item.get('knowledge_id', '<unknown>')} has incomplete source reference")
            elif (image_id, line_id) not in raw_lines:
                issues.append(f"{item.get('knowledge_id', '<unknown>')} references missing raw line {image_id}/{line_id}")

    for image in manifest.get("images", []):
        has_text = image.get("has_text")
        should_contribute = image.get("is_readable") and has_text is not False
        if should_contribute and image.get("id") not in contributed_images:
            issues.append(f"{image.get('id')} has no contribution in source_map")

    knowledge_items = knowledge_items_from_markdown(knowledge_text)
    if knowledge_items and len(source_items) < len(knowledge_items):
        issues.append(f"knowledge items exceed source_map items: {len(knowledge_items)} > {len(source_items)}")

    total_lines = max(1, len(raw_lines))
    uncertain_ratio = count_uncertain(raw_text + "\n" + knowledge_text) / total_lines
    if uncertain_ratio > uncertain_threshold:
        warnings.append(f"uncertain ratio {uncertain_ratio:.1%} exceeds {uncertain_threshold:.0%}")

    status = "FAIL" if issues else ("CONDITIONAL_PASS" if warnings else "PASS")
    report = {
        "status": status,
        "issues": issues,
        "warnings": warnings,
        "raw_line_count": len(raw_lines),
        "knowledge_item_count": len(knowledge_items),
        "source_map_item_count": len(source_items),
        "uncertain_ratio": uncertain_ratio,
    }
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "validation_report.json", report)
    write_validation_markdown(output_dir / "validation_report.md", report)
    return report


def write_validation_markdown(path: Path, report: Dict[str, Any]) -> None:
    lines = [
        f"# Validation Report: {report['status']}",
        "",
        f"- Raw lines: {report['raw_line_count']}",
        f"- Knowledge items: {report['knowledge_item_count']}",
        f"- Source map items: {report['source_map_item_count']}",
        f"- Uncertain ratio: {report['uncertain_ratio']:.1%}",
        "",
        "## Issues",
    ]
    lines.extend([f"- {item}" for item in report["issues"]] or ["- None"])
    lines.append("")
    lines.append("## Warnings")
    lines.extend([f"- {item}" for item in report["warnings"]] or ["- None"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Image-to-Knowledge skill helper CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("scaffold-run", help="create a standard run directory")
    p.add_argument("--base-dir", default=".", type=Path)
    p.add_argument("--run-id")

    p = sub.add_parser("preflight", help="read image metadata and write a manifest")
    p.add_argument("inputs", nargs="+")
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--run-id")

    p = sub.add_parser("crop", help="crop image regions from manifest and regions JSON")
    p.add_argument("--manifest", required=True, type=Path)
    p.add_argument("--regions", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--overlap-pct", type=float, default=0.05)
    p.add_argument("--scale", type=int, default=1)

    p = sub.add_parser("grid", help="generate fallback grid crops")
    p.add_argument("--manifest", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--rows", type=int, default=2)
    p.add_argument("--cols", type=int, default=2)
    p.add_argument("--overlap-pct", type=float, default=0.05)

    p = sub.add_parser("validate", help="validate raw extraction, knowledge doc, and source map")
    p.add_argument("--manifest", required=True, type=Path)
    p.add_argument("--raw", required=True, type=Path)
    p.add_argument("--knowledge", required=True, type=Path)
    p.add_argument("--source-map", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--uncertain-threshold", type=float, default=0.2)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "scaffold-run":
        result = run_scaffold(args.base_dir, args.run_id)
        print(result)
    elif args.command == "preflight":
        result = run_preflight(args.inputs, args.output_dir, args.run_id)
        print(json.dumps({"manifest": str(args.output_dir / f"{result['run_id']}_manifest.json"), "images": len(result["images"])}, ensure_ascii=False))
    elif args.command == "crop":
        result = run_crop(args.manifest, args.regions, args.output_dir, args.overlap_pct, args.scale)
        print(json.dumps({"crops": len(result["crops"]), "index": str(args.output_dir / "crops_index.json")}, ensure_ascii=False))
    elif args.command == "grid":
        result = run_grid(args.manifest, args.output_dir, args.rows, args.cols, args.overlap_pct)
        print(json.dumps({"crops": len(result["crops"]), "index": str(args.output_dir / "crops_index.json")}, ensure_ascii=False))
    elif args.command == "validate":
        result = run_validate(args.manifest, args.raw, args.knowledge, args.source_map, args.output_dir, args.uncertain_threshold)
        print(json.dumps({"status": result["status"], "report": str(args.output_dir / "validation_report.md")}, ensure_ascii=False))
        return 1 if result["status"] == "FAIL" else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
