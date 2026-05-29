#!/usr/bin/env python3
"""Batch convert BSH fault-tree PPTX decks to Flow-to-Knowledge manuals.

This follows the local reference skill:
  /Users/mac/Downloads/skill-BSH-Flow to Knowledge.md

It intentionally uses only the Python standard library. PPTX files are OpenXML
zip packages, so text and basic connector metadata can be read directly.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET


NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}

MARKER_TABLE = """| 标记 | 含义 |
|------|------|
| `【话术】` | 逐字朗读给用户的诊断引导话术 |
| `【判断】` | 根据用户回答或系统数据触发的条件分支 |
| `【诊断码】` | BSH 标准诊断码 |
| `【派工】` | 安排工程师上门 |
| `【配件】` | 预判所需配件 |
| `【视频】` | 视频辅助标记 |
| `【引用】` | 跨故障树引用跳转 |
| `【解释】` | 向用户解释原理/现象 |
| `【操作指导】` | 指导用户自行操作 |
| `▶` | 无条件进入下一步 |"""

PRODUCT_RULES = [
    ("各产品组安装操作指南", "INST", "安装操作指南", "Installation Guide"),
    ("对开门", "SBS", "对开门冰箱", "Side-by-Side"),
    ("微波烤箱", "MW", "微波炉", "Microwave"),
    ("抽屉蒸箱", "DSTM", "抽屉蒸箱", "Drawer Steamer"),
    ("普通冰箱", "FR", "普通冰箱", "Fridge"),
    ("制冷产品", "REF", "制冷产品", "Refrigeration"),
    ("酒柜", "WC", "酒柜", "Wine Cabinet"),
    ("洗衣机、洗干一体机", "WD", "洗衣机、洗干一体机", "Washer Dryer"),
    ("壁挂式洗衣机", "WMW", "壁挂式洗衣机", "Wall-mounted Washer"),
    ("洗衣机", "WM", "洗衣机", "Washing Machine"),
    ("洗干", "WD", "洗干一体机", "Washer Dryer"),
    ("干衣机", "DRY", "干衣机", "Dryer"),
    ("吸油烟机", "RH", "吸油烟机", "Range Hood"),
    ("烟机", "RH", "吸油烟机", "Range Hood"),
    ("蒸箱", "STM", "蒸箱", "Steamer"),
    ("烤箱", "OVEN", "烤箱", "Oven"),
    ("洗碗机", "DW", "洗碗机", "Dishwasher"),
    ("微蒸烤", "CMO", "微蒸烤", "Combi Microwave Oven"),
    ("微波", "MW", "微波炉", "Microwave"),
    ("燃气灶", "HOB", "燃气灶", "Gas Hob"),
    ("咖啡机", "CM", "咖啡机", "Coffee Machine"),
    ("Cookit", "CKT", "Cookit智能烹饪机", "Cookit"),
    ("智能烹饪机", "CKT", "智能烹饪机", "Cookit"),
    ("加热破壁机", "HB", "加热破壁机", "Heated Blender"),
    ("破壁机", "HB", "破壁机", "Heated Blender"),
    ("厨师机", "SM", "厨师机", "Stand Mixer"),
    ("吸尘器", "VC", "吸尘器", "Vacuum Cleaner"),
    ("嵌饮机", "BDM", "嵌饮机", "Built-in Drink Machine"),
    ("打蛋器", "HM", "打蛋器", "Hand Mixer"),
    ("料理机", "BLD", "料理机", "Blender"),
    ("暖碟", "WDW", "暖碟抽屉", "Warming Drawer"),
    ("消毒柜", "DCAB", "消毒柜", "Disinfection Cabinet"),
    ("电热水器", "EWH", "电热水器", "Electric Water Heater"),
    ("种植机", "PLT", "种植机", "Planter"),
    ("晶御智能咨询", "JY", "晶御智能咨询", "Smart Consulting"),
]

ISSUE_RULES = [
    ("检测不到咖啡豆", "检测不到咖啡豆", "CB"),
    ("咖啡豆箱", "检测不到咖啡豆", "CB"),
    ("检测不到水箱", "检测不到水箱", "WT"),
    ("检测不到水", "检测不到水", "WT"),
    ("水箱中是否有足够的水", "检测不到水箱", "WT"),
    ("不出咖啡", "不出咖啡", "CO"),
    ("不出热水", "不出热水", "HW"),
    ("奶泡问题", "奶泡问题", "MF"),
    ("奶泡效果不好", "奶泡效果不好", "MF"),
    ("不出奶泡", "不出奶泡", "NM"),
    ("过滤器无法取出", "过滤器无法取出", "FL"),
    ("钙化清洁", "钙化清洁", "CC"),
    ("异常显示或图标", "显示图标", "DI"),
    ("不通电", "不通电", "NP"),
    ("通电不工作", "通电不工作", "NS"),
    ("不工作", "不工作", "NWK"),
    ("不制冷", "不制冷", "NC"),
    ("不停机", "不停机", "CR"),
    ("报警", "报警", "AL"),
    ("噪音", "噪音", "NO"),
    ("异响", "异响", "NO"),
    ("结冰", "结冰结霜", "IF"),
    ("结霜", "结冰结霜", "IF"),
    ("积水", "积水", "WA"),
    ("漏水", "漏水", "WL"),
    ("冷凝水", "冷凝水", "CD"),
    ("照明灯", "照明灯异常", "LT"),
    ("灯", "灯异常", "LT"),
    ("按键", "按键异常", "BT"),
    ("按钮", "按键异常", "BT"),
    ("食物", "食物损坏", "FD"),
    ("不出冰块", "不出冰块", "NI"),
    ("不出冰水", "不出冰水", "NW"),
    ("显示异常", "显示异常", "DA"),
    ("E代码", "E代码", "EC"),
    ("E 代码", "E代码", "EC"),
    ("故障代码", "故障代码", "EC"),
    ("异味", "异味", "OD"),
    ("发热", "发热发烫", "HT"),
    ("发烫", "发热发烫", "HT"),
    ("门不平", "门不平", "DM"),
    ("门关不严", "门关不严", "DC"),
    ("门封", "门封紧", "DT"),
    ("门", "门异常", "DO"),
    ("漏胶", "漏胶", "GL"),
    ("烘干", "烘干效果差", "DR"),
    ("洗不干净", "洗不干净", "PC"),
    ("水垢", "水垢残留", "SC"),
    ("安装", "安装", "IN"),
    ("清洁", "清洁", "CL"),
    ("除垢", "除垢", "DS"),
    ("不加热", "不加热", "NH"),
    ("加热", "加热异常", "HT"),
]

CODE_ISSUE_RULES = [
    ("Coffee fill quantity inadequate", "检测不到咖啡豆", "CB"),
    ("Water tank empty", "检测不到水箱", "WT"),
    ("No coffee outlet", "不出咖啡", "CO"),
    ("No water dispensing", "不出热水", "HW"),
    ("No Power", "不通电", "NP"),
    ("Power supply available but no start", "通电不工作", "NS"),
    ("Milk beverage problems", "奶泡效果不好", "MF"),
    ("No milk", "不出奶泡", "NM"),
    ("Error code", "异常显示", "DA"),
    ("error display", "异常显示", "DA"),
    ("Descale/Clean", "清洁除垢", "CC"),
    ("Descale", "除垢", "DS"),
    ("Clean programm", "清洁", "CL"),
]

STOP_TEXT = {
    "BSH Home Appliances Group",
    "BSH Home Appliances Group Internal",
    "Internal",
    "Thanks",
    "THANKS",
}


@dataclass
class Shape:
    shape_id: str
    name: str
    text: str
    x: int
    y: int


@dataclass
class Slide:
    index: int
    xml_name: str
    texts: list[str]
    shapes: list[Shape]
    connectors: list[tuple[str, str, str]]


@dataclass
class Tree:
    number: int
    keyword: str
    prefix: str
    slides: list[Slide]
    filename: str = ""
    codes: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)

    @property
    def source_label(self) -> str:
        nums = [s.index for s in self.slides]
        if len(nums) == 1:
            return f"Slide {nums[0]}"
        return f"Slides {min(nums)}-{max(nums)}"


@dataclass
class Deck:
    path: Path
    product_code: str
    product_name: str
    product_basis: str
    version: str
    slides: list[Slide]
    filtered_slides: list[tuple[int, str]] = field(default_factory=list)
    trees: list[Tree] = field(default_factory=list)


def clean_text(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        item = clean_text(item)
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def md_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    rendered = ["| " + " | ".join(c.replace("|", "\\|").replace("\n", "<br>") for c in rows[0]) + " |"]
    rendered.append("| " + " | ".join("---" for _ in rows[0]) + " |")
    for row in rows[1:]:
        rendered.append("| " + " | ".join(c.replace("|", "\\|").replace("\n", "<br>") for c in row) + " |")
    return "\n".join(rendered)


def read_shape_text(element: ET.Element) -> str:
    return clean_text(" ".join(t.text or "" for t in element.findall(".//a:t", NS)))


def read_position(element: ET.Element) -> tuple[int, int]:
    xfrm = element.find(".//a:xfrm", NS)
    if xfrm is None:
        return 0, 0
    off = xfrm.find("a:off", NS)
    if off is None:
        return 0, 0
    return int(off.get("x", "0")), int(off.get("y", "0"))


def read_id_name(element: ET.Element) -> tuple[str, str]:
    c_nv_pr = element.find(".//p:cNvPr", NS)
    if c_nv_pr is None:
        return "", ""
    return c_nv_pr.get("id", ""), c_nv_pr.get("name", "")


def read_connector(element: ET.Element) -> tuple[str, str, str]:
    cid, name = read_id_name(element)
    start = element.find(".//a:stCxn", NS)
    end = element.find(".//a:endCxn", NS)
    return cid or name, start.get("id", "") if start is not None else "", end.get("id", "") if end is not None else ""


def parse_slide(name: str, payload: bytes, index: int) -> Slide:
    root = ET.fromstring(payload)
    shapes: list[Shape] = []
    for sp in root.findall(".//p:sp", NS):
        sid, sname = read_id_name(sp)
        text = read_shape_text(sp)
        x, y = read_position(sp)
        if text:
            shapes.append(Shape(sid, sname, text, x, y))
    shapes.sort(key=lambda s: (s.y, s.x, s.shape_id))
    connectors = [read_connector(cxn) for cxn in root.findall(".//p:cxnSp", NS)]
    return Slide(index=index, xml_name=name, texts=unique([s.text for s in shapes]), shapes=shapes, connectors=connectors)


def parse_pptx(path: Path) -> list[Slide]:
    with zipfile.ZipFile(path) as zf:
        names = sorted(
            [n for n in zf.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)],
            key=lambda n: int(re.search(r"slide(\d+)", n).group(1)),
        )
        return [parse_slide(name, zf.read(name), i) for i, name in enumerate(names, start=1)]


def infer_product(path: Path, first_slide: Slide | None) -> tuple[str, str, str]:
    haystack = path.stem
    if first_slide:
        haystack += " " + " ".join(first_slide.texts[:10])
    for key, code, name, basis in sorted(PRODUCT_RULES, key=lambda item: len(item[0]), reverse=True):
        if key in haystack:
            return code, name, basis
    digest = hashlib.sha1(path.stem.encode("utf-8")).hexdigest()[:4].upper()
    return f"P{digest}", path.stem, "filename-hash"


def infer_version(path: Path, first_slide: Slide | None) -> str:
    haystack = path.stem
    if first_slide:
        haystack += " " + " ".join(first_slide.texts[:20])
    match = re.search(r"V[\s_]*(\d+(?:\.\d+)?)", haystack, re.I)
    if match:
        return "V" + match.group(1)
    return "V1.0"


def is_filtered(slide: Slide) -> tuple[bool, str]:
    joined = " ".join(slide.texts)
    if slide.index == 1 and not re.search(r"请问|派工|ACC|跳转|[A-Z0-9]{12,13}", joined):
        return True, "封面/标题页"
    if re.search(r"Thanks|THANKS|谢谢", joined):
        return True, "结尾页"
    if re.search(r"版本记录|修改记录|变更历史", joined) and not re.search(r"请问|派工|ACC", joined):
        return True, "版本记录页"
    if not re.search(r"请问|派工|ACC|跳转|建议|观察|[A-Z0-9]{12,13}|[是否有无]", joined):
        return True, "无诊断逻辑页"
    return False, ""


def infer_issue(slide: Slide) -> tuple[str, str]:
    candidates = []
    for text in slide.texts[:30]:
        if text in STOP_TEXT:
            continue
        if re.search(r"Page|V\d|^\d+$|^\d+[-/]\d+[-/]\d+$", text, re.I):
            continue
        candidates.append(text)
    early_haystack = " ".join(candidates[:8])
    haystack = " ".join(candidates)
    for key, keyword, prefix in CODE_ISSUE_RULES:
        if key.lower() in haystack.lower():
            return keyword, prefix
    question_haystack = " ".join(t for t in candidates if "请问" in t or "？" in t or "?" in t)
    for key, keyword, prefix in sorted(ISSUE_RULES, key=lambda item: len(item[0]), reverse=True):
        if key in question_haystack:
            return keyword, prefix
    for key, keyword, prefix in sorted(ISSUE_RULES, key=lambda item: len(item[0]), reverse=True):
        if key in early_haystack:
            return keyword, prefix
    for key, keyword, prefix in sorted(ISSUE_RULES, key=lambda item: len(item[0]), reverse=True):
        if key in haystack:
            return keyword, prefix
    for text in candidates:
        if len(text) <= 12 and not text.startswith("请问"):
            keyword = re.sub(r"[问题故障异常]+$", "", text)[:6] or text[:6]
            return keyword, "FX"
    return f"第{slide.index}页", "FX"


def collect_tree_data(tree: Tree) -> None:
    texts = unique([text for slide in tree.slides for text in slide.texts])
    tree.codes = unique(re.findall(r"\b[A-Z0-9]{12,13}\b", " ".join(texts)))
    tree.questions = unique([t for t in texts if "请问" in t or "？" in t or "?" in t])[:12]
    tree.actions = unique([
        t for t in texts
        if any(k in t for k in ["派工", "ACC", "建议", "观察", "安排", "联系", "视频", "需要配件", "跳转", "接受", "不接受"])
    ])[:20]
    tree.references = unique(re.findall(r"跳转[“\"']?([^”\"'\s]+)", " ".join(texts)))


def group_trees(slides: list[Slide]) -> tuple[list[Tree], list[tuple[int, str]]]:
    filtered: list[tuple[int, str]] = []
    process: list[tuple[Slide, str, str]] = []
    for slide in slides:
        drop, reason = is_filtered(slide)
        if drop:
            filtered.append((slide.index, reason))
            continue
        keyword, prefix = infer_issue(slide)
        process.append((slide, keyword, prefix))

    trees: list[Tree] = []
    for slide, keyword, prefix in process:
        if trees and trees[-1].keyword == keyword:
            trees[-1].slides.append(slide)
            continue
        trees.append(Tree(number=len(trees) + 1, keyword=keyword, prefix=prefix, slides=[slide]))

    used_prefix: dict[str, int] = {}
    for tree in trees:
        used_prefix[tree.prefix] = used_prefix.get(tree.prefix, 0) + 1
        if used_prefix[tree.prefix] > 1:
            tree.prefix = f"{tree.prefix}{used_prefix[tree.prefix]}"
        collect_tree_data(tree)
    return trees, filtered


def keywords_for_tree(tree: Tree) -> list[str]:
    base = [tree.keyword]
    joined = " ".join(t for slide in tree.slides for t in slide.texts)
    for token in re.findall(r"[A-Z]\d{1,4}|[\u4e00-\u9fff]{2,8}", joined):
        if token in {"请问", "是否", "机器", "用户", "故障树", "建议您"}:
            continue
        if len(token) <= 8:
            base.append(token)
    synonyms = {
        "不通电": ["没有电", "黑屏", "灯不亮"],
        "不制冷": ["不凉", "温度高", "食物化了"],
        "报警": ["嘀嘀响", "蜂鸣", "报警灯闪"],
        "噪音": ["声音大", "异响", "嗡嗡响"],
        "漏水": ["地上有水", "底部漏水"],
        "门关不严": ["门关不上", "门弹开"],
    }
    base.extend(synonyms.get(tree.keyword, []))
    return unique(base)[:8]


def safe_mermaid(text: str) -> str:
    text = text.replace("[", "(").replace("]", ")").replace("{", "(").replace("}", ")").replace("|", "/")
    return text[:70] or "节点"


def mermaid(tree: Tree) -> tuple[str, list[tuple[str, str, str, str]]]:
    prefix = tree.prefix
    questions = tree.questions or [f"确认用户主诉是否为{tree.keyword}？"]
    actions = tree.actions
    lines = ["flowchart TD", f"    {prefix}_START([用户报修：{safe_mermaid(tree.keyword)}]) --> {prefix}_D01"]
    lookup: list[tuple[str, str, str, str]] = [("入口", f"{prefix}_START", "起始", f"用户报修：{tree.keyword}")]
    for i, question in enumerate(questions, start=1):
        node = f"{prefix}_D{i:02d}"
        next_node = f"{prefix}_D{i+1:02d}" if i < len(questions) else f"{prefix}_OUT"
        connector = "{" + f"D{i:02d}\\n{safe_mermaid(question)}" + "}"
        if i == 1:
            lines.append(f"    {node}{connector}")
        else:
            lines.append(f"    {node}{connector}")
        action = actions[i - 1] if i - 1 < len(actions) else "继续按源页判断"
        if i < len(questions):
            lines.append(f"    {node} -->|用户回答匹配源页分支| {next_node}")
            lines.append(f"    {node} -->|用户无法确认/不接受| {prefix}_MANUAL{i:02d}[转人工/派工确认]")
            lookup.append((f"D{i:02d}", node, "判断", f"{next_node} / {prefix}_MANUAL{i:02d}"))
        else:
            lines.append(f"    {node} -->|可自助处理/用户接受| {prefix}_ACC([ACC/观察/指导完成])")
            lines.append(f"    {node} -->|无法处理/用户不接受| {prefix}_DISPATCH([【派工】按诊断码记录])")
            lookup.append((f"D{i:02d}", node, "判断", f"{prefix}_ACC / {prefix}_DISPATCH"))
        if action:
            lines.append(f"    {node} -.源页动作.-> {prefix}_NOTE{i:02d}[{safe_mermaid(action)}]")
    if len(questions) == 0:
        lines.append(f"    {prefix}_D01 --> {prefix}_DISPATCH([【派工】按源页判断])")
    lookup.extend([
        ("结束-ACC", f"{prefix}_ACC", "结束", "用户接受/观察/指导完成"),
        ("结束-派工", f"{prefix}_DISPATCH", "派工", "无法处理或用户不接受"),
    ])
    return "\n".join(lines), lookup


def tree_steps(tree: Tree) -> str:
    questions = tree.questions or [f"请问您的情况是否属于“{tree.keyword}”？"]
    parts: list[str] = []
    for i, question in enumerate(questions, start=1):
        node = f"{tree.prefix}_D{i:02d}"
        next_label = f"D{i+1:02d}" if i < len(questions) else "ACC / 派工"
        rows = [
            ["条件", "下一步", "出口类型", "Mermaid 边验证"],
            ["用户回答匹配源页下一分支", next_label, "继续诊断", f"{node} → {next_label}（自动草案，待视觉确认）"],
            ["用户接受解释/操作/观察", "结束", "ACC", f"{node} → ACC（待视觉确认）"],
            ["用户不接受 / 无法操作 / 风险场景", "派工或转人工", "派工", f"{node} → DISPATCH（待视觉确认）"],
            ["**兜底越界**：其他无法识别的输入", "越界协议", "越界", "无对应 Mermaid 边"],
        ]
        parts.append(f"""### D{i:02d} — {clean_text(question)[:32]}

**[节点：{node}]**

**【话术】**：
> "{question}"

**判断表**：

{md_table(rows)}
""")
    if tree.actions:
        parts.append("### 源页动作/结果摘录\n\n" + "\n".join(f"- {a}" for a in tree.actions))
    return "\n\n".join(parts)


def tree_file(deck: Deck, tree: Tree) -> str:
    mer, lookup = mermaid(tree)
    code_summary = " / ".join(f"`{c}`" for c in tree.codes) if tree.codes else "`源页未抽取到明确诊断码`"
    rows_lookup = [["步骤", "节点 ID", "节点类型", "简述"]] + [list(r) for r in lookup]
    code_rows = [["诊断码", "描述", "触发步骤", "备注"]]
    if tree.codes:
        for code in tree.codes:
            code_rows.append([f"`{code}`", "见源 PPT 相邻文本", "源页派工/判断节点", "自动抽取，待人工核对英文/中文描述"])
    else:
        code_rows.append(["源页未抽取到明确诊断码", "—", "—", "待人工补充"])
    dispatch_rows = [["配件名称", "关联步骤", "说明"]]
    dispatch_rows.append(["待工程师上门判断" if any("需要配件" in a for a in tree.actions) else "源页未明确", "派工出口", "按源 PPT 派工节点记录，待视觉确认"])
    ref_rows = [["引用方向", "触发条件", "目标文件", "目标诊断码"]]
    if tree.references:
        for ref in tree.references:
            ref_rows.append([f"本树 → {ref}", "源页出现跳转提示", "待索引映射", "—"])
    else:
        ref_rows.append(["无明确跨树引用", "—", "—", "—"])
    all_text = unique([t for s in tree.slides for t in s.texts])
    source_excerpt = "\n".join(f"- {t}" for t in all_text[:120])
    return f"""# BSH {deck.product_name} — {tree.keyword} 诊断手册

**故障编号**：F{tree.number:02d} | **节点前缀**：{tree.prefix} | **来源**：PPT {tree.source_label}
**适用诊断码**：{code_summary}
**转换状态**：自动批处理草案，需按源 PPT 视觉关系复核后生产使用

---

## 一、文档使用说明

### 三条执行铁律

1. **不越界**：只执行本文件定义的诊断步骤；遇到超出范围的问题，执行越界协议（见第三节），不得自行延伸
2. **不编造**：话术原文不得改写、补充或省略；不在本文件中的诊断码不得使用
3. **不跳步**：严格按 D 步骤顺序执行，不得跳过中间步骤直接给出结论

### 执行约定标记表

{MARKER_TABLE}

---

## 二、故障诊断导航树

### Mermaid 源码

```mermaid
{mer}
```

### 诊断步骤 ↔ 节点速查表

{md_table(rows_lookup)}

---

## 三、越界处理协议

### 触发条件（满足以下任意一条即触发越界）

| # | 触发场景 |
|---|---------|
| 1 | 用户故障描述无法映射到当前诊断树的任何入口分支 |
| 2 | 用户回答无法映射到当前 D 步骤的任何条件行 |
| 3 | 目标跳转节点在 Mermaid 图中无有效连线或仍需视觉确认 |
| 4 | 用户要求提供本文档未包含的信息，如价格、保修政策、投诉升级 |
| 5 | 用户描述涉及焦味、冒烟、漏电、跳闸、进水等安全风险 |
| 6 | 用户要求自行拆机、维修、改线或更换内部零部件 |

### 退出动作

- 若属于其他故障树：执行 `【引用】` 跳转或回到索引重新分流
- 若无法定位：转人工客服
- 若存在安全风险：停止在线指导并安排工程师或人工处理

### 严禁行为

- 严禁自行判断主板、电源板、电机、压缩机等内部零部件级故障
- 严禁改写源 PPT 话术作为确定结论
- 严禁在用户尚未回答当前问题时跳至下一步

### 覆盖范围

本故障树仅覆盖 `{tree.keyword}` 相关诊断。其他故障现象应回到 `{deck.product_code}` 索引重新分流。

---

## 四、诊断入口

### 故障主诉确认

- 用户描述与 `{tree.keyword}` 相关。
- 命中索引关键词：{", ".join(keywords_for_tree(tree)[:6])}。
- 来源页：{tree.source_label}。

### 入口分支判断

```
用户报修“{tree.keyword}”
│
├── 主诉匹配当前树 → 进入 D01
├── 主诉属于其他故障 → 回到索引执行跨树引用
└── 主诉不明确 → 先追问具体显示/部位/现象
```

---

## 五、诊断步骤详情

{tree_steps(tree)}

---

## 附录 A：诊断码汇总表

{md_table(code_rows)}

---

## 附录 B：配件建议汇总表

{md_table(dispatch_rows)}

---

## 附录 C：跨故障树引用清单

{md_table(ref_rows)}

---

## 附录 D：源页文本摘录（用于复核）

{source_excerpt}
"""


def index_file(deck: Deck) -> str:
    file_rows = [["编号", "文件名", "故障类型", "Mermaid 节点前缀", "PPT 来源页"]]
    keyword_rows = [["用户描述关键词", "分流到文件", "备注"]]
    ref_rows = [["来源文件", "引用目标文件", "触发条件"]]
    for tree in deck.trees:
        file_rows.append([f"F{tree.number:02d}", f"`{tree.filename}`", tree.keyword, f"`{tree.prefix}`", tree.source_label])
        keyword_rows.append(["、".join(keywords_for_tree(tree)[:6]), f"F{tree.number:02d} {tree.keyword}", "自动抽取关键词，待人工扩充同义词"])
        for ref in tree.references:
            ref_rows.append([f"F{tree.number:02d} {tree.keyword}", ref, "源页出现跳转提示"])
    if len(ref_rows) == 1:
        ref_rows.append(["无明确跨故障树引用", "—", "—"])
    filtered = "、".join(f"Slide {i}（{r}）" for i, r in deck.filtered_slides) or "无"
    return f"""# BSH {deck.product_name} 故障诊断索引 {deck.version}

---

## 一、使用说明

### 本索引用途

本索引是 LLM 执行 {deck.product_name} 故障诊断的**一级分诊入口**。当用户描述故障现象时，LLM 应首先查阅本索引的“一级分流表”，定位到对应的故障树文件，然后加载该文件执行诊断。

### 文件体系说明

- **本文件**（索引）：`BSH_{deck.product_code}_{deck.version}_index.md` — 分流入口，不含具体诊断逻辑
- **独立故障树文件**：`BSH_{deck.product_code}_F{{nn}}_{{故障关键词}}.md` — 每棵故障树的完整诊断手册

### 分流执行方法

1. 用户描述故障现象
2. 在“一级分流表”中匹配关键词，确定目标故障树文件
3. 加载对应文件，从该文件的“诊断入口”开始执行
4. 若诊断过程中遇到跨树引用（`【引用】`），切换到目标文件继续

### 三条执行铁律

1. **不越界**：只执行当前加载的故障树文件中定义的诊断步骤，遇到超出范围的情况执行越界协议
2. **不编造**：话术原文不得改写、补充或省略；不在文件中的诊断码不得使用
3. **不跳步**：严格按 D 步骤顺序执行，不跳过中间步骤直接给出结论

---

## 二、文件清单

{md_table(file_rows)}

**被过滤的非流程页**：{filtered}

---

## 三、一级分流表

{md_table(keyword_rows)}

---

## 四、跨故障树引用关系

{md_table(ref_rows)}

---

## 五、产品系列与适用机型

- **产品系列代码**：`{deck.product_code}`（{deck.product_basis}，自动推断）
- **来源文档**：`{deck.path.name}`
- **文档版本**：{deck.version}
- **适用机型**：{deck.product_name} 相关机型
- **知识手册生成日期**：{date.today().isoformat()}
- **转换状态**：自动批处理草案，需按源 PPT 视觉关系复核
"""


def safe_filename_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "", name)[:20] or "未命名"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def write_deck(deck: Deck, out_root: Path) -> dict[str, object]:
    out_root.mkdir(parents=True, exist_ok=True)
    for tree in deck.trees:
        tree.filename = f"BSH_{deck.product_code}_F{tree.number:02d}_{safe_filename_name(tree.keyword)}.md"
        write_text(out_root / tree.filename, tree_file(deck, tree))
    index_name = f"BSH_{deck.product_code}_{deck.version}_index.md"
    write_text(out_root / index_name, index_file(deck))
    return {
        "source_file": str(deck.path),
        "product_code": deck.product_code,
        "product_name": deck.product_name,
        "version": deck.version,
        "tree_count": len(deck.trees),
        "index_file": index_name,
    }


def validate_output_dir(out_root: Path) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    required = [
        "## 一、文档使用说明",
        "## 二、故障诊断导航树",
        "## 三、越界处理协议",
        "## 四、诊断入口",
        "## 五、诊断步骤详情",
        "## 附录 A：诊断码汇总表",
        "## 附录 B：配件建议汇总表",
        "## 附录 C：跨故障树引用清单",
        "```mermaid",
        "兜底越界",
    ]
    for path in sorted(out_root.glob("BSH_*_F*.md")):
        text = path.read_text(encoding="utf-8")
        missing = [r for r in required if r not in text]
        results.append({"file": str(path), "status": "PASS" if not missing else "WARN", "missing": ";".join(missing)})
    return results


def write_reports(out_root: Path, summaries: list[dict[str, object]]) -> None:
    report_rows = [["source_file", "product_code", "product_name", "version", "tree_count", "index_file"]]
    for s in summaries:
        report_rows.append([str(s[k]) for k in ["source_file", "product_code", "product_name", "version", "tree_count", "index_file"]])
    write_text(out_root / "BATCH_RESULT_REPORT.md", "# BSH Flow to Knowledge Batch Report\n\n" + md_table(report_rows))

    qa_rows = [["file", "status", "missing"]]
    for row in validate_output_dir(out_root):
        qa_rows.append([row["file"], row["status"], row["missing"]])
    write_text(out_root / "QUALITY_CHECK_REPORT.md", "# Quality Check Report\n\n" + md_table(qa_rows))

    jsonl = out_root / "batch_summary.jsonl"
    with jsonl.open("w", encoding="utf-8") as fh:
        for s in summaries:
            fh.write(json.dumps(s, ensure_ascii=False) + "\n")
    with (out_root / "batch_summary.csv").open("w", encoding="utf-8", newline="") as fh:
        fields = ["source_file", "product_code", "product_name", "version", "tree_count", "index_file"]
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for s in summaries:
            writer.writerow({k: s[k] for k in fields})

    manifest_fields = [
        "filename",
        "doc_type",
        "product_code",
        "product_name",
        "version",
        "fault_no",
        "fault_keyword",
        "content",
    ]
    rows: list[dict[str, str]] = []
    for path in sorted(out_root.glob("BSH_*.md")):
        text = path.read_text(encoding="utf-8")
        name = path.name
        index_match = re.fullmatch(r"BSH_([^_]+)_(V[^_]+)_index\.md", name)
        fault_match = re.fullmatch(r"BSH_([^_]+)_F(\d{2})_(.+)\.md", name)
        row = {
            "filename": name,
            "doc_type": "index" if index_match else "fault_tree",
            "product_code": "",
            "product_name": "",
            "version": "",
            "fault_no": "",
            "fault_keyword": "",
            "content": text,
        }
        if index_match:
            row["product_code"] = index_match.group(1)
            row["version"] = index_match.group(2)
            title = text.splitlines()[0] if text.splitlines() else ""
            row["product_name"] = title.replace("# BSH ", "").split(" 故障诊断索引")[0]
        elif fault_match:
            row["product_code"] = fault_match.group(1)
            row["fault_no"] = f"F{fault_match.group(2)}"
            row["fault_keyword"] = fault_match.group(3)
            title = text.splitlines()[0] if text.splitlines() else ""
            row["product_name"] = title.replace("# BSH ", "").split(" — ")[0]
        rows.append(row)
    with (out_root / "database_upload_manifest.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (out_root / "database_upload_manifest.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=manifest_fields)
        writer.writeheader()
        writer.writerows(rows)


def make_unique_codes(decks: list[Deck]) -> None:
    seen: dict[str, int] = {}
    for deck in decks:
        key = deck.product_code
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1:
            deck.product_code = f"{deck.product_code}{seen[key]}"


def main() -> int:
    parser = argparse.ArgumentParser()
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--input-root", type=Path)
    input_group.add_argument("--input-file", type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    out_root = args.output_root.expanduser().resolve()
    if args.clean and out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    if args.input_file:
        input_file = args.input_file.expanduser().resolve()
        if input_file.suffix.lower() != ".pptx":
            raise SystemExit(f"--input-file must be a .pptx file: {input_file}")
        pptx_files = [input_file]
    else:
        input_root = args.input_root.expanduser().resolve()
        pptx_files = sorted(input_root.rglob("*.pptx"))
    decks: list[Deck] = []
    for path in pptx_files:
        slides = parse_pptx(path)
        code, product, basis = infer_product(path, slides[0] if slides else None)
        version = infer_version(path, slides[0] if slides else None)
        trees, filtered = group_trees(slides)
        deck = Deck(path=path, product_code=code, product_name=product, product_basis=basis, version=version, slides=slides, filtered_slides=filtered, trees=trees)
        decks.append(deck)

    make_unique_codes(decks)
    summaries = [write_deck(deck, out_root) for deck in decks]
    write_reports(out_root, summaries)
    archive = shutil.make_archive(str(out_root), "zip", root_dir=out_root)
    print(json.dumps({"pptx_count": len(pptx_files), "output_root": str(out_root), "archive": archive, "summaries": summaries}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
