# Image-to-Knowledge Workflow

## Step 0: Preflight

Run `preflight` on every image batch. The manifest assigns stable IDs starting at `IMG-01`, records dimensions, format, readability, and low-resolution enhancement recommendations.

Images that are unreadable stay in the manifest but are skipped in later deterministic processing.

## Step 1: Global Recognition

Read each image once as a whole. Output:
- Content type: selling-point overview, function detail, parameter table, exterior/product photo, or other
- Layout: single column, multi-column, table, or mixed text/image
- Regions with approximate percentage coordinates
- Lines under each region using `[region-line]` IDs

Do not summarize at this stage. The raw extraction must stay close to the visible image text.

## Step 2: Enhancement Decision

Enhance if any trigger applies:

| Trigger | Meaning |
|---|---|
| T1 | Width below 1200px or height below 800px |
| T2 | Small text or dense text region |
| T3 | Dense table, usually 5+ rows or 4+ columns |
| T4 | Dark, gradient, or image-overlaid background |
| T5 | Global recognition has obvious missing text or many uncertain lines |
| T6 | Same fact appears with conflicting recognition results |
| T7 | User explicitly asks for higher precision |

If unsure, enhance. For low-risk images with clear large text and five or fewer text regions, skip enhancement.

## Step 3: Cropping and Enhanced Recognition

Use `crop` when Step 1 produced usable region coordinates. `regions.json` must use:

```json
{
  "IMG-01": [
    {
      "region_id": "A",
      "name": "标题区",
      "x_start_pct": 0,
      "x_end_pct": 100,
      "y_start_pct": 0,
      "y_end_pct": 15
    }
  ]
}
```

Use `grid` when coordinates are unreliable. Start with `2x2`; use `3x3` for very dense or long images.

Recognition allocation:
- Prefer independent region recognition in parallel, up to four workers at a time.
- Each worker handles one to three regions.
- If no multi-agent or parallel tool exists, do independent serial passes: do not expose prior pass text to the next pass, then compare afterward.

## Step 4: Cross-Validation

Compare global recognition, crop recognition, and independent passes.

Adoption rules:
- All sources agree: high confidence.
- At least two-thirds agree: adopt majority, note minority difference.
- Two sources disagree: keep the richer text only if it does not contradict the other; otherwise mark uncertainty.
- No majority: keep all candidates and mark `【待用户确认】`.

Line IDs may drift between passes. Align by region, visual order, text similarity, keywords, and numbers; do not rely only on line number.

## Step 5: Knowledge Formatting

Format only after raw extraction is complete.

Use structures such as:
- Product overview: title, positioning, selling points
- Function detail: function group, subpoints
- Parameter table: Markdown table preserving rows, columns, units, blank cells
- Mixed material: hierarchy matching the visual information architecture

The knowledge document may reorganize and deduplicate, but every substantive item must have source-map coverage.

## Step 6: Validation and User Confirmation

Run `validate` after writing raw extraction, knowledge doc, and source map.

Status rules:
- `PASS`: no blocking issues and uncertainty is within threshold.
- `CONDITIONAL_PASS`: no missing provenance, but uncertainty is high; include待确认清单.
- `FAIL`: missing source map items, broken source references, or images with expected text but no contribution.

Do not call a `FAIL` result complete.
