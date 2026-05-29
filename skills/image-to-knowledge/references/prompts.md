# Prompt Templates

## Global Recognition

```text
You are extracting source text from a product or business material image.

Return raw extraction only. Do not summarize, rewrite, translate, or infer missing text.

Output Markdown:
## 【整体识别】IMG-XX

### 区域 A：<region name>（x=<start-end>%, y=<start-end>%）
- [A-1] <visible original text>
- [A-2] <visible original text>

Rules:
1. Assign visual regions by layout logic: title, feature block, parameter table, note, footer.
2. Estimate region percentage coordinates. If unsure, mark the coordinate as approximate.
3. Preserve model numbers, units, punctuation, footnotes, and blank table cells.
4. Mark uncertainty as （识别不确定：A / B）.
5. Do not add knowledge-document headings yet.
```

## Region Recognition

```text
You are independently recognizing cropped image regions.

You may not use or rely on any prior recognition result. Read only the provided crop image(s).

Output Markdown lines only:
### 区域 <ID>：<name if known>
- [<ID>-1] <visible original text>
- [<ID>-2] <visible original text>

Rules:
1. Keep original wording.
2. One logical text block per line.
3. Preserve numbers, units, model names, and table labels exactly.
4. Mark uncertainty as （识别不确定：A / B）.
5. End with ===识别结束===.
```

## Cross-Validation

```text
You are comparing multiple OCR/VLM recognition passes for the same image material.

Inputs:
- Global raw extraction
- Enhanced crop extraction(s)
- Independent pass extraction(s)

Tasks:
1. Align lines by image, region, visual order, text similarity, keywords, and numbers.
2. Do not rely only on line ID because line splitting may differ.
3. Produce consensus text that preserves original wording.
4. List additions, corrections, conflicts, and unresolved candidates.
5. Mark unresolved conflicts with 【待用户确认】.

Adoption:
- All sources agree: high confidence.
- At least two-thirds agree: adopt majority and note minority difference.
- No majority: keep all candidates.
- Enhanced result missing a global line: keep the global line unless visually contradicted.
```

## Knowledge Formatting

```text
You are formatting a source-traceable knowledge document from raw extraction.

Use only the supplied raw extraction and consensus notes. Do not add external facts or inferred claims.

Output:
1. Knowledge Markdown with clear sections.
2. Source map JSON matching references/output-contract.md.
3. 待确认清单 for every unresolved or low-confidence item.

Rules:
- Preserve factual wording from raw extraction.
- Deduplicate repeated facts only when meaning and values match.
- Parameter tables must preserve rows, columns, units, blank cells, and model relationships.
- Every substantive bullet, table row, or factual statement must have a source_map item.
```
