# Output Contract

## File Names

Use:
- `{run_id}_manifest.json`
- `{brand}_{series}_Kxx_raw_extraction.md`
- `{brand}_{series}_Kxx_知识库.md`
- `{brand}_{series}_Kxx_source_map.json`
- `{brand}_{series}_Kxx_validation_report.md`

Brand should be an uppercase English brand or accepted abbreviation. `Kxx` starts at `K01` and increments only when creating a separate knowledge document.

## Raw Extraction Format

Raw extraction is the source of truth. Use visible original wording only.

```markdown
# BOSCH 空间大师沸石款 Raw Extraction

## 【整体识别】IMG-01

### 区域 A：标题区（x=0-100%, y=0-15%）
- [A-1] 空间大师沸石款核心卖点一览
- [A-2] （识别不确定：博世 / 博仕）

### 区域 B：洗净区（x=20-60%, y=20-50%）
- [B-1] 高能除菌专区
- [B-2] 精准定位洗
```

Rules:
- Every line must have `[A-1]` style line IDs.
- Restart line IDs within each region.
- Keep uncertainty inline with `（识别不确定：A / B）`.
- Do not remove footnotes, units, model numbers, or table labels.

## Knowledge Document Format

The knowledge document is structured for retrieval and reading.

```markdown
# BOSCH 空间大师沸石款洗碗机知识库

## 核心卖点
- 高能除菌专区
- 精准定位洗

## 待确认清单
| 序号 | 位置 | 当前内容 | 不确定原因 |
|---|---|---|---|
| 1 | IMG-01 A-2 | 博世 / 博仕 | 字形相近 |
```

Rules:
- Use raw extraction wording.
- Do not invent section content.
- If deduplicating repeated text, source map may cite multiple sources for one knowledge item.
- Tables must preserve model names, values, units, empty cells, row labels, and column order.

## Source Map Schema

```json
{
  "document": "BOSCH_空间大师沸石款_K01_知识库.md",
  "raw_extraction": "BOSCH_空间大师沸石款_K01_raw_extraction.md",
  "items": [
    {
      "knowledge_id": "K-001",
      "section": "核心卖点",
      "text": "高能除菌专区",
      "sources": [
        {
          "image_id": "IMG-01",
          "region_id": "B",
          "line_id": "B-1"
        }
      ]
    }
  ]
}
```

Rules:
- `items` must not be empty for a non-empty knowledge document.
- Every substantive bullet, table row, or factual statement must have a source item.
- `image_id` and `line_id` must exist in raw extraction.
- `region_id` must match the line ID prefix where practical.

## Validation Report

The validation report must include:
- Status: `PASS`, `CONDITIONAL_PASS`, or `FAIL`
- Missing source references
- Images with expected text but zero contribution
- Uncertainty ratio
- Pending user confirmations

`FAIL` blocks delivery. `CONDITIONAL_PASS` requires the待确认清单 to be visible in the knowledge document or final response.
