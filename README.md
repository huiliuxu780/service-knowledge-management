# service-knowledge-management

BSH 售后服务知识库（安装 / 故障诊断 / 产品培训）— 多文件、Git 管理、可上传到火山引擎大模型知识库。

---

## 目录结构

```
.
├── README.md                    # 本文件
├── .gitignore
│
├── skills/                      # AI Skill 定义（仅放方法论，不放代码）
│   ├── bsh-install-to-knowledge/   # PDF 安装指南 → 多文件知识树
│   ├── bsh-flow-to-knowledge/      # PPT 故障树 → 多文件知识树
│   └── image-to-knowledge/         # 图片 → 知识图卡（带 references/）
│
├── tools/                       # 可执行脚本（CI / 人工运行）
│   └── image_to_knowledge.py
│
├── install/                     # 安装类知识库（按批次版本）
│   └── v2026.01/                # 一份 PDF 覆盖全产品 → 一个版本目录
│       ├── _index.md            # 全局路由索引
│       └── BSH_INST_I01_洗衣机.md … I16_净饮机.md
│
├── fault-diagnosis/             # 故障诊断知识库（按产品组，git 管版本）
│   ├── BDM_嵌饮机/
│   ├── BLD_料理机/
│   ├── CKT_智能烹饪机/
│   ├── CM_咖啡机/               # 含 BSH_CM_*（V1.1）和 BSH_CM2_*（V1.0）
│   ├── CMO_微蒸烤一体机/
│   ├── DCAB_消毒柜/
│   ├── DRY_干衣机/
│   ├── DSTM_抽屉蒸箱/
│   ├── DW_洗碗机/               # 含 BSH_DW_* 与 BSH_DW2_*
│   ├── EWH_电热水器/
│   ├── FR_冰箱/
│   ├── HB_加热破壁机/
│   ├── HM_打蛋器/
│   ├── HOB_燃气灶/
│   ├── INST_安装故障诊断/        # 安装相关的故障诊断（与 install/ 不同：这里是排障视角）
│   ├── JY_晶御智能咨询/
│   ├── MW_微波炉/               # 含 BSH_MW_* 与 BSH_MW2_*
│   ├── OVEN_烤箱/               # 含 BSH_OVEN_* 与 BSH_OVEN2_*
│   ├── PLT_种植机/
│   ├── REF_制冷产品/
│   ├── RH_吸油烟机/             # 含 BSH_RH_* 与 BSH_RH2_*
│   ├── SM_厨师机/
│   ├── STM_蒸箱/                # 含 BSH_STM_* 与 BSH_STM2_*
│   ├── VC_吸尘器/
│   ├── WC_酒柜/
│   ├── WD_洗衣机/
│   ├── WDW_暖碟抽屉/
│   └── WMW_壁挂洗衣机/
│
├── product-training/            # 产品培训知识库（与故障树语义隔离，避免污染排障路径）
│   └── DW_洗碗机/
│       └── BOSCH_空间大师&灵动大师洗碗机_K01_知识库.md
│
└── manifests/                   # 部署元数据（上传记录、清单、报告）
    ├── volcengine/
    │   ├── fault-diagnosis.jsonl          # 故障诊断知识库上传清单
    │   └── fault-diagnosis-summary.jsonl  # 批处理摘要
    ├── bsh-flow-batch-report.md           # 故障树批处理报告
    ├── bsh-flow-omission-audit.md         # 漏文审计
    └── bsh-flow-quality-check.md          # 质量检查
```

---

## 治理规则（请保持，不要破坏）

1. **`skills/` 只放 Skill 定义**（SKILL.md + references/）。可执行代码一律放 `tools/`。
2. **`tools/` 不放数据**，只放脚本；输入路径以参数形式传入。
3. **`install/` 按批次版本**（一份 PDF 一个 `v*/` 目录），扁平存放产品树 + `_index.md` 全局路由。
4. **`fault-diagnosis/` 按产品组**（一个产品一个目录），目录名采用 `CODE_中文名` 双重命名：
   - `CODE` 作为程序化访问主键（来自原 PPT 的产品代号）；
   - `中文名` 给运营/工程师肉眼识别。
   - 同一产品多个来源 PPT（如 `DW` + `DW2`）合并到同一目录，各自保留 `BSH_<CODE>_V*_index.md`。
5. **`product-training/` 不与 `fault-diagnosis/` 混放**——不同语义召回路径，混放会污染排障 agent 的检索结果。
6. **`manifests/` 只放 JSONL，不放完整 CSV**；ZIP 包不进主分支。
7. **中间产物**（`bsh_pdf_work/`、`outputs/`、`runs/`、`*.png`、`*.pptx` 等）由 `.gitignore` 排除。

---

## 命名约定

| 类别 | 格式 | 示例 |
|---|---|---|
| 安装树文件 | `BSH_INST_I<NN>_<产品>.md` | `BSH_INST_I04_冰箱.md` |
| 故障树文件 | `BSH_<CODE>_F<NN>_<故障名>.md` | `BSH_DW_F01_不通电.md` |
| 故障树索引 | `BSH_<CODE>_V<版本>_index.md` | `BSH_DW_V1.0_index.md` |
| 安装索引 | `_index.md` | `install/v2026.01/_index.md` |
| 产品目录 | `<CODE>_<中文名>` | `DW_洗碗机` |

---

## 工作流

### 新增一份故障树（PPT → KB）
1. 用 `skills/bsh-flow-to-knowledge/` 处理 PPT，得到扁平输出。
2. 按产品 CODE 移入 `fault-diagnosis/<CODE_中文名>/`。
3. 更新 `manifests/volcengine/fault-diagnosis.jsonl`（或新增对应产品的清单）。
4. `git commit` —— 故障树版本由 git 管理，不需要全局 `v*/`。

### 新增一份安装指南（PDF → KB）
1. 用 `skills/bsh-install-to-knowledge/` 处理 PDF。
2. 创建 `install/v<新版本>/`，扁平存放 16 个产品树 + `_index.md`。
3. 旧版本目录保留只读，不就地修改。

### 同步到火山引擎
1. 读取 `manifests/volcengine/*.jsonl`。
2. 用 `tools/volcengine_kb_import.py`（待补）按清单上传。
3. 上传后更新清单的 checksum / upload_at 字段并 commit。

---

## 待补 / TODO

- [ ] `skills/bsh-flow-to-knowledge/SKILL.md` 待补充（原始 Skill 文件未在此次迁移中入库）
- [ ] `tools/bsh_flow_to_knowledge_batch.py` 批处理脚本入库
- [ ] `tools/volcengine_kb_import.py` 火山引擎自动上传脚本
- [ ] 为 `install/v2026.01/` 也生成 `manifests/volcengine/install-v2026.01.jsonl`
