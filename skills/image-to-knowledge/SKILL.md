---
name: image-to-knowledge
description: Use when converting product screenshots, marketing slides, parameter-table images, or image-based business materials into source-traceable Markdown knowledge documents.
metadata:
  short-description: Convert image materials into traceable knowledge docs
---

# Image to Knowledge

Convert text-heavy product or business images into Markdown knowledge documents with strict provenance. The final knowledge document is not accepted unless every substantive item can be traced back to raw extraction lines.

## When to Use

Use for:
- Product selling-point screenshots, PPT slide images, posters, and marketing pages
- Product parameter comparison tables captured as images
- Detail-page screenshots with text and layout structure
- Incremental image batches for an existing product knowledge document

Do not use for:
- Pure photos with no readable text
- Pixel-perfect OCR tasks such as invoices, IDs, or legal scans
- Editable PPT, Word, Excel, or PDF sources that can be read directly
- Fault trees, diagnostic trees, or process diagrams; use the relevant flow-to-knowledge skill instead

## Required Workflow

1. Create or choose a run directory. Use `scripts/image_to_knowledge.py scaffold-run` when a new run folder is needed.
2. Run preflight before recognition:
   ```bash
   python3 scripts/image_to_knowledge.py preflight <image-or-dir> --output-dir <run>/work --run-id <run_id>
   ```
3. Perform visual recognition and write `*_raw_extraction.md` first. Raw extraction must be organized by `IMG-xx`, region, and line IDs such as `[A-1]`.
4. If small text, dense tables, low resolution, dark backgrounds, uncertainty, or user request triggers enhancement, create region crops with `crop`. If region coordinates are unreliable, create fallback grid crops with `grid`.
5. Merge recognition results by comparing global recognition, enhanced regions, and any independent passes. If multi-agent tooling is unavailable, perform independent multi-pass recognition without reading previous pass conclusions, then merge afterward.
6. Write `*_知识库.md` only from raw extraction content. Do not introduce facts that are not in raw extraction.
7. Write `*_source_map.json` and run `validate`. Fix FAIL results before calling the document complete.

## Mandatory Outputs

Each run must produce:
- `{run_id}_manifest.json`
- `{brand}_{series}_Kxx_raw_extraction.md`
- `{brand}_{series}_Kxx_知识库.md`
- `{brand}_{series}_Kxx_source_map.json`
- `{brand}_{series}_Kxx_validation_report.md`

The raw extraction is the source of truth. The knowledge document may reorganize content but must not rewrite values, add facts, or hide uncertainty.

## References

- Read `references/workflow.md` for Step 0-6 execution details and enhancement triggers.
- Read `references/output-contract.md` before writing raw extraction, knowledge docs, source maps, or validation reports.
- Read `references/prompts.md` when constructing global recognition, region recognition, cross-validation, or formatting prompts.

## Helper CLI

The helper script is deterministic and zero-dependency-first:
- Uses Python standard library by default
- Uses macOS `sips` for image metadata and cropping when Pillow is unavailable
- Uses Pillow automatically if it is installed

Commands:
```bash
python3 scripts/image_to_knowledge.py scaffold-run --base-dir ./runs --run-id RUN001
python3 scripts/image_to_knowledge.py preflight ./input --output-dir ./runs/RUN001/work --run-id RUN001
python3 scripts/image_to_knowledge.py crop --manifest ./runs/RUN001/work/RUN001_manifest.json --regions ./runs/RUN001/work/regions.json --output-dir ./runs/RUN001/crops
python3 scripts/image_to_knowledge.py grid --manifest ./runs/RUN001/work/RUN001_manifest.json --output-dir ./runs/RUN001/crops/grid --rows 2 --cols 2
python3 scripts/image_to_knowledge.py validate --manifest ./runs/RUN001/work/RUN001_manifest.json --raw ./runs/RUN001/output/BOSCH_x_K01_raw_extraction.md --knowledge ./runs/RUN001/output/BOSCH_x_K01_知识库.md --source-map ./runs/RUN001/output/BOSCH_x_K01_source_map.json --output-dir ./runs/RUN001/output
```

## Quality Rules

- Preserve original wording for extracted text. Mark uncertainty instead of guessing.
- Keep raw extraction and knowledge formatting separate.
- For tables, preserve model names, numbers, units, blank cells, and column relationships.
- For conflicts, keep candidates and mark `【待用户确认】`.
- A validation status of `FAIL` blocks delivery. `CONDITIONAL_PASS` can be delivered only with a visible待确认清单.
