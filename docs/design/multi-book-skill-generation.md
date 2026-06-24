# Multi-book Skill Generation Design

## 背景

当前 `book2skills` 的核心链路是：上传一本书，解析、分块、抽取 Knowledge Units，再生成模块化 skill 和 router，最后打包为可安装的 `skills.zip`。

下一阶段可以先做 **Multi-book Skill Generation**，但暂时不引入完整知识图谱。用户选择多本已处理完成的书，系统把它们作为一个 collection，复用或抽取每本书的 Knowledge Units，做跨书归一化、聚类、冲突检测和来源引用，最终生成一个综合 skill。

这个功能的目标不是“多本书总结”，而是从一个小型书库里提炼出可执行的方法论 skill。

## 产品目标

### 跨书提炼共识

多本书反复出现的原则、流程和实践，应该被提升为更稳定的综合方法论。

例如 5 本产品书都提到用户访谈、需求验证、MVP、增长模型，系统应将这些重复出现的知识提炼成更可信的实践型 skill，而不是简单拼接每本书的观点。

### 保留分歧和流派

多本书经常会对同一问题给出不同建议。好的综合 skill 不应该把冲突观点磨平成平均值，而应该保留适用边界。

例如：

- A 书的方法适合创业早期。
- B 书的方法适合大公司流程。
- C 书强调某类常见反例。

最终 skill 应该能告诉 agent：在什么情况下采用哪一种路线，以及这些路线背后的来源依据。

### 形成领域方法论

单书 skill 容易像一本书的读书笔记。多书 skill 应该更像一个领域知识包：围绕真实任务组织知识，形成可执行流程、判断条件、模板和注意事项。

## 产品入口

前端新增顶层概念：`Collections`。

现有结构：

```text
Library
  -> Book
    -> Chat
    -> Generate Skill
```

新增后：

```text
Library
  -> Books
  -> Collections
      -> Select books
      -> Configure generation
      -> Generate collection skill
      -> Preview / refine / pack / download
```

## 前端页面设计

### `/library`

保留当前书籍列表，同时增加 `New Collection Skill` 入口。

只允许选择 `status === "ready"` 的书进入 collection skill 生成流程。

### `/collections/new`

新建 collection 的页面。

字段：

- `name`：collection 名称，例如“产品方法论合集”。
- `description`：collection 描述。
- `book_ids`：多选已 ready 的书。

高级选项：

- `reuse_extracted_kus`：是否复用已有 KU，默认 true。
- `detect_conflicts`：是否检测冲突与流派，默认 true。

生成目标不绑定在 collection 创建阶段。`user_goal` 应放在后续 generate request 中，以便同一个 collection 可以针对不同目标重新生成 skill。

### `/collections/[collectionId]`

Collection 详情页。

展示内容：

- collection 基本信息。
- 包含的书籍列表。
- 每本书的处理状态和 KU 可用状态。
- collection skill 生成状态：`draft`、`generating`、`ready`、`error`。
- 生成后的跨书主题、共识、分歧和来源引用摘要。

### `/collections/[collectionId]/skills/[skillId]`

Collection skill 详情页。

可复用当前单书 skill 详情页的大部分交互：

- 预览 `SKILL.md`。
- pack。
- download。
- refine。
- playground。

区别：

- 路由和面包屑指向 collection。
- 数据来源从单本 book 变成 collection。
- 页面应展示 source corpus，即本 skill 来自哪些书。

## 后端数据模型

当前 `SkillPackage` 强绑定 `book_id`。Multi-book skill 不建议硬塞进单书模型，推荐新增 collection 相关表。

### `collections`

```text
id
user_id
name
description
status
created_at
updated_at
```

状态建议：

```text
draft | active | archived
```

`Collection.status` 只描述书单自身是否可用，不描述 skill 生成任务。书籍是否 ready 通过关联 books 的状态实时判断；skill 生成状态由 `CollectionSkillPackage.status` 表达。

### `collection_books`

```text
collection_id
book_id
order_index
```

用于记录 collection 包含哪些书，以及用户选择顺序。

### `collection_skill_packages`

```text
id
collection_id
user_id
skill_md
scripts
templates
zip_path
version
status
created_at
updated_at
```

状态建议：

```text
draft | generating | ready | error
```

第一版运行中间产物可以先放在 `CollectionSkillPackage.scripts` JSONB 中，不必急着拆成完整知识图谱表。

注意：`CollectionSkillPackage` 是一次 generate run 一条记录，因此其中的 `scripts` 只适合保存本次运行的 checkpoint 和快照。任何承诺跨运行、跨加书、跨版本稳定的 identity registry，不能只存在于 package-level scripts 中。

建议保存：

```text
source_kus.json
ku_similarity_candidates.json
normalized_ku_groups.json
same_as_edges.json
deduped_view.json
themes.json
consensus.json
candidate_tensions.json
citations.json
pipeline_phase
```

Checkpoint 建议按阶段明确写入，避免 Phase 4/5 失败后从头重跑：

```text
pipeline_phase = "source_kus_loaded"
source_kus.json

pipeline_phase = "normalized_kus_ready"
ku_similarity_candidates.json
normalized_ku_groups.json
same_as_edges.json
deduped_view.json

pipeline_phase = "themes_ready"
themes.json

pipeline_phase = "consensus_ready"
consensus.json

pipeline_phase = "candidate_tensions_ready"
candidate_tensions.json

pipeline_phase = "skill_modules_ready"
modules.json

pipeline_phase = "router_ready"
router.json

pipeline_phase = "ready"
skill_md
citations.json
```

重试时应先读取 `pipeline_phase`，复用已经完成的 JSON 产物，只从缺失阶段继续执行。

### Collection-level Identity Store

R-Phase 5+ 需要一个独立于单次 generate run 的 collection-level identity store，用来保持 `claim_key`、KU identity edge 和 claim identity edge 的稳定性。

推荐模型：

```text
CollectionClaimIdentity
id
collection_id
claim_key
canonical_question
canonical_statement
aliases JSONB
status                 # candidate | confirmed | deprecated
confidence
first_seen_run_id
created_at
updated_at
```

```text
CollectionIdentityEdge
id
collection_id
edge_type              # same_as | alias_of
from_type              # ku | claim | claim_key
from_id
to_type
to_id
confidence
evidence_claim_ids JSONB
evidence_ku_ids JSONB
source_book_ids JSONB
status                 # candidate | confirmed | review_required | deprecated
flags JSONB            # e.g. ["split_after_claim_analysis"]
decided_by
created_in_run_id
created_at
```

`CollectionSkillPackage.scripts` 可以保存这些 registry / edges 在某次 run 中使用到的快照，便于打包和审计；但 collection-level store 才是跨版本 diff 和增量更新的 source of truth。

## API 设计

新增 `backend/app/api/routes/collections.py`。

### Collection API

```text
GET    /api/collections
POST   /api/collections
GET    /api/collections/{collection_id}
PATCH  /api/collections/{collection_id}
DELETE /api/collections/{collection_id}
POST   /api/collections/{collection_id}/generate
GET    /api/collections/{collection_id}/status
```

`POST /api/collections` request:

```json
{
  "name": "产品方法论合集",
  "description": "从多本产品书提炼可执行方法论",
  "book_ids": ["...", "..."]
}
```

`POST /api/collections/{collection_id}/generate` request:

```json
{
  "reuse_extracted_kus": true,
  "detect_conflicts": true,
  "user_goal": "适合早期创业团队做需求验证"
}
```

第一版不提供 `target_skill_count`。现有聚类基于 UMAP + HDBSCAN，无法稳定指定簇数量。后续如果需要控制模块数量，应增加 `max_modules` 作为生成后的合并/裁剪策略，而不是承诺固定聚类数。

### Collection Skill API

```text
GET    /api/collection-skills/{skill_id}
POST   /api/collection-skills/{skill_id}/pack
GET    /api/collection-skills/{skill_id}/download
```

也可以把 collection skill API 放在 `/api/skills/collections/...` 下，但建议独立命名，避免和当前 `/api/skills/books/{book_id}/generate` 混淆。

## 后端 Pipeline

新增 Celery task：`generate_collection_skill_task`。

### Phase 0: Validate

- 检查 collection 存在。
- 检查 collection 至少包含 2 本书。
- 检查所有 books 都是 `ready`。
- 创建 `CollectionSkillPackage`，状态置为 `generating`。

### Phase 1: Load Or Extract KUs

优先复用每本书已有的 KU：

- 从当前书最近的 `SkillPackage.scripts["extracted_kus.json"]` 或 `extracted_kus_partial.json` 读取。
- 如果没有可复用 KU，则使用现有单书 pipeline 的检索和抽取逻辑补齐。

每个 KU 需要附加 source metadata：

```text
book_id
book_title
author
chapter_num
source_chunk_id
source_label
```

第一版不要直接修改现有 `KnowledgeUnit` 的基础字段，以免影响单书 extraction、dedup、cluster 的兼容性。Collection pipeline 使用包装结构承载来源：

```text
SourceBackedKnowledgeUnit
- ku: KnowledgeUnit
- source:
  - book_id
  - book_title
  - author
  - chapter_num
  - source_chunk_id
  - source_label
```

需要传入现有 `ClusterGenerator` 时，只传其中的 `ku`；需要生成 citations、consensus、tensions 时，使用 wrapper 上的 source metadata。

### Phase 2: Cross-book Normalization

跨书归一化应结合 embedding 和 LLM judge，但不能做销毁式合并。

目标：

- 识别语义重复或高度相似的 KU。
- 保留所有来源引用。
- 不丢失不同书中的细微差异。
- 为后续 KG 沉淀 `same_as` / `alias_of` 候选关系。

核心原则是 **link-and-keep**：

- 原始 KU 永远保留在 `source_kus.json`。
- embedding similarity 只做 blocking，产出候选相似组。
- LLM / agent judge 决定候选是否真的表达同一方法、原则或步骤。
- 判定为 same 的 KU 不互相覆盖，而是形成归一化 group 和显式关系。
- skill 生成可以读取折叠后的 view，但这个 view 是派生产物，不是唯一事实来源。

当前已落地的第一步只生成 embedding similarity 候选和非销毁式折叠视图；LLM / agent judge 的确认、拆分和 review flag 进入后续 claim/identity 阶段。

新增或调整工件：

```text
source_kus.json
ku_similarity_candidates.json
normalized_ku_groups.json
same_as_edges.json
deduped_view.json
```

`source_kus.json` 保存所有带来源的原始 KU。`deduped_view.json` 才是供 theme clustering / skill generation 使用的折叠视图。

`normalized_ku_groups.json` 示例：

```json
{
  "group_id": "ku_group_customer_discovery_interview",
  "canonical_ku_id": "ku-book-a-12",
  "member_ku_ids": ["ku-book-a-12", "ku-book-b-33"],
  "canonical_fields": {
    "principle": "...",
    "method": "...",
    "step_by_step": []
  },
  "variant_terms": ["customer discovery", "problem interview", "需求验证访谈"],
  "source_refs": [
    {"book_id": "book-a", "chunk_id": "book-a-chunk-12"},
    {"book_id": "book-b", "chunk_id": "book-b-chunk-33"}
  ],
  "confidence": 0.86,
  "decided_by": "llm_judge"
}
```

`same_as_edges.json` 示例：

```json
{
  "from_ku_id": "ku-book-a-12",
  "to_ku_id": "ku-book-b-33",
  "relationship": "same_as",
  "confidence": 0.86,
  "evidence": "两者都描述通过访谈验证客户问题是否真实存在。",
  "decided_by": "llm_judge"
}
```

`deduped_view.json` 中的 canonical KU：

```text
principle
method
step_by_step
example
when_to_use
sources[]
variants[]
```

跨书归一化不能复用单书 `KUProcessor.deduplicate_kus()` 或当前 `semantic_deduplicate_kus()` 的“相似就丢弃 / 留长丢短”策略。Collection 场景需要非销毁式派生视图：

- 先用 embedding similarity 找候选重复组。
- 对每组候选用 LLM judge 判断是否表达同一方法、原则或步骤。
- canonical 字段优先选择信息最完整、步骤最可执行的一条 KU，或由多条 KU 派生。
- 其他 KU 不丢弃，保留为 `source_kus.json` 的原始记录，并在 `deduped_view.json` 中折叠为 `variants[]`。
- 所有来源都合并进 `sources[]`，同时保留 `same_as_edges.json` 解释为什么这些 KU 被折叠。
- 若两个 KU 相似但适用条件明显不同，不合并为重复项，而交给 tension detection。
- 阈值不能作为最终裁决；例如 0.9 只能进入候选队列，不能直接决定删除或合并。

### Phase 3: Theme Clustering

复用现有 `ClusterGenerator` 的思路，但输入改为 `deduped_view.json` 中的折叠视图。

聚类结果不再代表单书章节主题，而是跨书方法论模块。

示例：

- 用户访谈。
- 需求验证。
- MVP 实验。
- 增长循环。
- 指标体系。
- 组织协作。

### Phase 4: Consensus Extraction

对每个 theme 提取多书共同支持的内容。

输出：

```text
theme_name
common_principles
repeated_steps
shared_when_to_use
evidence_sources
confidence
```

`confidence` 可以先用简单规则估算：

- 支持该观点的书籍数量。
- 来源 KU 数量。
- 是否来自不同作者或不同章节。

第一版 confidence 使用归一化规则，避免不同 collection 规模下不可比较：

```text
book_support_ratio = supporting_book_count / total_book_count
ku_support_ratio = min(supporting_ku_count / 5, 1.0)
confidence = round(0.7 * book_support_ratio + 0.3 * ku_support_ratio, 2)
```

其中 `supporting_book_count` 是支持该共识的去重后书籍数量，`supporting_ku_count` 是支持该共识的 KU 数量。

### Phase 5: Tension / School Detection

对每个 theme 检测分歧、冲突和适用边界。

常见分歧类型：

- 产品阶段不同：创业早期、增长期、成熟期。
- 组织规模不同：个人、小团队、大公司。
- 风险偏好不同：快速试错、流程治理、长期品牌。
- 操作顺序不同：先访谈、先数据、先原型。
- 价值观不同：用户直觉、数据驱动、战略定位。

输出：

```text
theme_name
tension
position_a
position_b
source_refs
synthesis_guidance
when_to_choose_a
when_to_choose_b
```

### Phase 6: Generate Modular Skills

每个 theme 生成一个 `ModularSkill`。

相比单书 skill，collection skill 的每个模块都应包含：

- 共识原则。
- 默认推荐流程。
- 分歧与流派。
- 情境判断。
- 反例和注意事项。
- 来源引用。

### Phase 7: Generate Master Router

Router 不再按章节或单书主题组织，而是按用户任务场景组织。

示例：

```text
"不知道用户真正要什么" -> User_Interview_Discovery
"想验证 MVP" -> MVP_Experiment_Design
"团队已经进入增长阶段" -> Growth_Loop_Diagnostics
"多个产品机会无法排序" -> Opportunity_Prioritization
```

### Phase 8: Persist And Pack

保存：

- `skill_md`
- modular skills
- router
- scripts 中的中间产物
- templates
- citations

Collection skill 第一版不写现有 `Skill` 表。当前 `Skill.book_id` 是非空外键，直接复用会迫使 collection skill 填一个假的单书 ID。第一版通过 `CollectionSkillPackage.skill_md/scripts/templates` 和 collection skill API 完成交付。

如果后续需要把 collection skill 写入共享 `skills_vectors` 检索库，再单独设计 `Skill.book_id` nullable、`Skill.collection_id` 或新建 `CollectionSkill` 表，不在第一版混入。

打包时使用 collection storage directory，例如：

```text
storage/collections/{collection_id}/skills_{skill_id}.zip
```

## Prompt 设计

新增 prompts：

```text
backend/app/prompts/normalize_cross_book_kus.md
backend/app/prompts/extract_consensus_and_tensions.md
backend/app/prompts/generate_collection_modular_skill.md
backend/app/prompts/generate_collection_router.md
```

### `normalize_cross_book_kus.md`

职责：

- 判断多个 KU 是否表达同一方法、原则或步骤。
- 输出 normalized groups、same_as candidate / confirmed edges 和 `deduped_view`。
- 保留原始 KU、variants 和所有 sources。

### `extract_consensus_and_tensions.md`

职责：

- 对同一 theme 内的 KU 提炼共识。
- 检测冲突观点。
- 写清不同观点的适用条件。
- 输出可引用的 source refs。

### `generate_collection_modular_skill.md`

职责：

- 将一个 theme 转成可执行 skill module。
- 必须包含共识、分歧、适用条件、步骤和来源。
- 禁止把冲突观点强行综合成空泛表述。

### `generate_collection_router.md`

职责：

- 从所有模块生成 master router。
- 将用户任务场景映射到对应模块。
- 说明多个模块同时适用时的执行顺序。

## Skill 输出结构

最终 `SKILL.md` 建议结构：

```text
# Product Discovery and Validation Skill

## When To Use

## Source Corpus
- Book A
- Book B
- Book C

## Core Consensus

## Decision Map

## Skills

### 1. User Interview Discovery
- Consensus
- Workflow
- Divergences / Schools
- Use This Approach When
- Sources

### 2. MVP Experiment Design

## Caveats
```

这样可以明显区别于单本书读书笔记。

## 前端 API 封装

在 `frontend/src/lib/api.ts` 增加：

```ts
export async function createCollection(...)
export async function listCollections()
export async function getCollection(collectionId: string)
export async function generateCollectionSkill(collectionId: string, options?: ...)
export async function getCollectionSkill(skillId: string)
export async function packCollectionSkill(skillId: string)
export function getCollectionSkillDownloadUrl(skillId: string)
```

现有 `generateSkill(bookId)` 保留，不要和 collection skill 混在一起。

## 可复用模块

可以直接复用或少量改造：

- `KnowledgeExtractor`
- `ClusterGenerator`
- `SkillGenerator`
- `RouterGenerator`
- `SkillPacker`
- 当前 skill preview/refine/playground UI

建议新增：

- `CollectionKUProvider`
- `CrossBookNormalizer`
- `ConsensusTensionAnalyzer`
- `CollectionSkillGenerator`
- `CollectionRouterGenerator`

## 第一版范围

第一版要做：

- 多选已 ready 的书。
- 创建 collection。
- 复用或抽取 KU。
- 跨书归一化。
- 跨书聚类。
- 共识与分歧检测。
- 生成 collection skill。
- pack 和 download。

第一版暂不做：

- 知识图谱 UI。
- 图数据库。
- NotebookLM 导入。
- 多用户权限。
- 图谱可视化。
- 实时 pipeline 细分进度。

## 分阶段实现计划

建议拆成 5 个主要 plan，每个 plan 都应能独立验证。可选的第 6 个 plan 用于增强自动补抽 KU 和失败恢复能力。

### Plan 1: Collection 基础模型与 API

目标：先让系统认识“书单”。

范围：

- 新增 `Collection`、`CollectionBook` 模型。
- 新增 Alembic migration。
- 新增 collection 相关 schemas。
- 新增 `/api/collections` CRUD。
- 支持创建 collection、列出 collection、查看详情、添加书、移除书。
- 校验只能加入 `ready` 的书。

验收标准：

- 可以通过 API 创建一个 collection。
- 可以把多本 ready books 加进去。
- 可以查看 collection 详情。
- 不涉及 skill 生成。

### Plan 2: Collection Skill 数据模型与基础页面

目标：把多书 skill 的容器建好。

范围：

- 新增 `CollectionSkillPackage` 模型。
- 新增 Alembic migration。
- 新增 `/api/collection-skills/{skill_id}` 查询接口。
- 新增 collection skill pack/download 接口，或先接入 `SkillPacker` 的最小可用版本。
- 前端新增 `/collections/new`。
- 前端新增 `/collections/[collectionId]`。
- Library 页面增加 Collections 入口。
- 前端可以创建 collection 并看到详情。

验收标准：

- 用户能在 UI 里新建 collection。
- collection detail 能展示所选书籍。
- 后端存在 collection skill package 的数据容器。
- 还不需要真的生成 skill。

### Plan 3: KU 聚合与跨书归一化 Pipeline

目标：打通 collection skill 生成的前半段。

范围：

- 新增 `generate_collection_skill_task`。
- 新增 `CollectionKUProvider`。
- 从 `book_knowledge_units` 读取每本书的权威 KU；`scripts/extracted_kus.json` 只作为审查/打包快照。
- 给 KU 附加 `book_id`、`book_title`、`author`、`chapter_num`、`source_chunk_id` 等 source metadata。
- 新增 `CrossBookNormalizer`。
- 保存中间产物：
  - `source_kus.json`
  - `ku_similarity_candidates.json`
  - `normalized_ku_groups.json`
  - `same_as_edges.json`
  - `deduped_view.json`
  - `pipeline_phase`

第一版对 KU 缺失的处理可以先保守一些：如果某本书没有可复用 KU，返回明确错误，提示先生成单书 skill。自动补抽 KU 可放到后续增量更新与知识资产生命周期阶段。

验收标准：

- 触发 collection generate 后，能创建 collection skill package 记录。
- 能从多本书加载 KU。
- 能生成非销毁式 normalization 工件和供下游使用的 `deduped_view.json`。
- `source_kus.json`、`normalized_ku_groups.json`、`same_as_edges.json` 和 `deduped_view.json` 被保存到 scripts。
- 不要求生成最终 `SKILL.md`。

### Plan 4: 共识/分歧分析与 Collection Skill 生成

目标：把“多书综合价值”做出来。

范围：

- 复用 `ClusterGenerator` 做跨书 KU 聚类。
- 新增 `ConsensusTensionAnalyzer`。
- 新增 prompts：
  - `normalize_cross_book_kus.md`
  - `extract_consensus_and_tensions.md`
  - `generate_collection_modular_skill.md`
  - `generate_collection_router.md`
- 新增 `CollectionSkillGenerator`。
- 新增 `CollectionRouterGenerator`。
- 生成最终 `skill_md`、modules、router、citations。
- 更新 collection skill package 状态为 `ready` 或 `error`。

验收标准：

- 多本书能生成一个完整 collection skill。
- 输出中明确包含：
  - `Source Corpus`
  - `Core Consensus`
  - `Divergences / Schools`
  - `Decision Map`
  - modular skills
- scripts 中保存：
  - `themes.json`
  - `consensus.json`
  - `candidate_tensions.json`
  - `citations.json`

## Post-v1 Roadmap

当前已经完成的 v1 能跑通 collection skill 生成、运行历史、失败可见性、重试、pack/download。后续路线不再以“轻量版”作为产品目标，而是直接面向最终形态：

```text
多本书 -> 观点级知识建模 -> 跨书观点关系 -> 场景化方法论 -> 可执行 skill -> 可交互知识系统 -> 知识图谱
```

工程上分 phase，是为了降低风险和成本，不代表目标降级。

### R-Phase 5: Collection Skill Quality Improvements

目标：让 collection skill 从“多书内容合集”升级为“领域方法论系统”。

#### Claim 层由谁产生

Claim 层不是用户手写，也不是 Codex Skill 直接写入数据库的自由文本。它由 collection generation pipeline 编排产生：

- **来源输入**：`book_knowledge_units` 中的书级 KU，以及 R-Phase 3/4 已生成的 theme、consensus、candidate tension 工件。
- **生产者**：后端新增的 collection-level analyzer，例如 `ClaimExtractor`、`ClaimAligner`、`ClaimRelationshipClassifier`、`ApplicationBoundaryGenerator`。这些组件可以调用配置好的 LLM provider；如果未来允许 agent-assisted review，也只能作为 judge/reviewer 参与，不直接绕过后端契约写库。
- **编排者**：`generate_collection_skill_task` 或拆分后的 collection pipeline task。它负责分阶段调用 analyzer、checkpoint、失败恢复和状态更新。
- **结构真源**：后端 schema / store。`structured_claims.json`、`claim_relationships.json` 等必须由后端校验后写入 run artifacts；稳定 identity 必须写入 collection-level identity store。
- **人工/agent 角色**：用于复核、修正或批准 identity/relationship 判断。修正以 append-friendly 的 identity edge 或 review flag 形式记录，不覆盖原始 KU 和原始 claim。

换句话说，agent 可以帮助判断“这两个 claim 是否同一观点”“这两个观点是什么关系”，但 claim 层的生成和持久化边界仍属于 Book2Skills 后端 pipeline。这样才能避免出现第二套 claim schema 或不可追踪的图谱身份。

核心原则：

- 保持现有 `theme -> module` 生成链路可用，不在第一步破坏已跑通的 pipeline。
- 对全局 KU 做 claim 对齐，但只 emit 至少来自 2 本书的 claim group，优先处理真正有跨书信号的部分。
- 只对跨书重叠 claim group 抽取 structured claims，控制 LLM 成本。
- 不把 structured claim 字段塞进 `KnowledgeUnit` schema；它们是 collection 级分析产物，应落在 `scripts` 工件中。
- `claim_identity_registry` 和最终要审计的 `same_as` / `alias_of` identity edges 必须持久化在 collection-level store 中；`CollectionSkillPackage.scripts` 只保存本次 run 的快照。
- 关系判断先避免强断言“明确冲突”，但允许记录 `conflict_candidate` 供后续验证。

新增工件：

```text
structured_claims.json
claim_identity_registry.json
aligned_claim_groups.json
claim_relationships.json
application_boundaries.json
decision_rules.json
```

#### `structured_claims.json`

按来源 KU 索引的结构化观点，不改 `KnowledgeUnit` schema。

示例：

```json
{
  "source_chunk_id": "book-a-chunk-12",
  "source_book_id": "book-a",
  "claim_key": "decision_making_under_uncertainty",
  "question": "在不确定情况下如何做决策？",
  "position": "先小步行动，用反馈修正判断",
  "reasoning": "行动能降低信息不确定性",
  "recommended_action": "设计低成本实验",
  "conditions": ["高不确定", "试错成本低"],
  "risks": ["可能行动过快，忽略系统性风险"],
  "source_refs": [
    {
      "book_id": "book-a",
      "title": "A 书",
      "chapter_num": 3,
      "chunk_id": "book-a-chunk-12"
    }
  ]
}
```

#### `claim_identity_registry.json`

`claim_key` 是观点身份，不只是 LLM 临时生成的标签。它必须能跨运行、跨加书、跨版本稳定复用，否则 R-Phase 8 图谱和 R-Phase 9 版本 diff 会退化成模糊文本比较。

规则：

- `claim_key` 由 registry 分配或复用，不由单次 prompt 自由发明。
- 新 claim 进入时，先用 embedding / lexical key 找候选，再由 agent judge 判断是否复用已有 `claim_key`。
- 不确定时创建 `candidate` 身份，不强行合并。
- `same` 关系可以折叠到同一个 canonical claim node，但必须保留 identity 决策证据。
- registry 是 append-friendly 的派生工件；修正身份时新增映射/边，不覆盖原始 claim。
- 每次 generate 可以在 package scripts 中保存 registry snapshot；跨运行 source of truth 必须写回 collection-level identity store。

示例：

```json
{
  "claim_key": "decision_making_under_uncertainty",
  "canonical_question": "在不确定情况下如何做决策？",
  "canonical_statement": "根据试错成本和可逆性选择先行动实验或先验证前提。",
  "aliases": [
    "uncertainty_decision",
    "high_uncertainty_action_vs_validation"
  ],
  "source_claim_ids": ["claim-1", "claim-9"],
  "confidence": 0.88,
  "status": "confirmed",
  "first_seen_run_id": "run-2026-06-22-001"
}
```

`same_as_claim_keys` 不作为 `CollectionClaimIdentity` 的冗余列存储；它是从 `CollectionIdentityEdge(edge_type="same_as", from_type/to_type in {"claim", "claim_key"})` 派生出的视图字段。

#### `aligned_claim_groups.json`

全局 claim 对齐结果。只输出至少来自 2 本书的 group。

示例：

```json
{
  "claim_key": "decision_making_under_uncertainty",
  "question": "在不确定情况下如何做决策？",
  "source_book_ids": ["book-a", "book-b"],
  "claim_ids": ["claim-1", "claim-9"],
  "theme_refs": ["Problem_Solving_Framework"]
}
```

#### KU Identity 与 Claim Identity 的关系

Phase 2 的 `same_as_edges.json` 是 KU 级归一化，回答“两个来源 KU 是否表达同一方法/原则/步骤”。R-Phase 5 的 `claim_identity_registry.json` 是 claim 级身份，回答“多个观点是否属于同一个可长期追踪的问题/判断点”。

规则：

- KU-level `same_as` 可以为 claim-level identity 提供候选证据，但不能自动决定 `claim_key`。
- `claim_key` 是更高阶的稳定身份；多个 KU same group 可以映射到同一个 claim identity，也可以拆成多个 claim identity。
- 如果两个 KU 被判为 `same_as`，但它们抽出的 claims 被 agent judge 分配到不同 `claim_key`，以 claim-level registry 为准，并在 identity edge 上记录 `review_required` 或 `split_after_claim_analysis`。
- 如果两个 claims 被判为 same / alias，但其底层 KU 没有 same edge，可以补写 claim-level `same_as` / `alias_of` edge，不反向强改 KU-level 判断。
- R-Phase 8 图谱同时保留 KU-level same edge 与 claim-level identity edge；展示层可以折叠，审计层必须可展开。

#### `claim_relationships.json`

对同一个 claim group 中不同书的观点做关系分类。

关系类型：

```text
same
complementary
contextual
tension
conflict_candidate
```

说明：

- `same`：观点基本一致，只是术语不同。
- `complementary`：观点互补，可以组合。
- `contextual`：观点取决于场景、阶段、约束。
- `tension`：观点之间存在张力，需要在使用前做取舍。
- `conflict_candidate`：疑似明确冲突，但不在自动生成中强断言为“已确认冲突”。

示例：

```json
{
  "claim_key": "decision_making_under_uncertainty",
  "relationship": "contextual",
  "summary": "A 书强调先行动获取反馈，B 书强调先验证前提。二者不是直接冲突，而是适用于不同风险水平。",
  "views": [
    {
      "book_id": "book-a",
      "position": "先行动，再修正",
      "best_for": ["低成本试错", "信息不足"]
    },
    {
      "book_id": "book-b",
      "position": "先建模，再验证",
      "best_for": ["高风险决策", "不可逆选择"]
    }
  ]
}
```

#### `application_boundaries.json`

把关系判断转译成适用边界。

示例：

```json
{
  "claim_key": "decision_making_under_uncertainty",
  "use_view_a_when": ["试错成本低", "需要快速获取反馈"],
  "use_view_b_when": ["决策不可逆", "错误成本高"],
  "combine_when": ["需要先验证关键前提，再用实验推进"],
  "warning": "不要把快速行动误用到高风险不可逆决策中。"
}
```

#### `decision_rules.json`

面向最终 skill 的可执行规则。

示例：

```json
{
  "rule": "如果场景是高不确定、低试错成本，采用小步实验；如果场景是高风险、不可逆决策，先做前提验证。",
  "claim_key": "decision_making_under_uncertainty",
  "source_book_ids": ["book-a", "book-b"]
}
```

最终 skill 侧 R-Phase 5 的交付：

- 保持现有 theme/module 生成不动。
- 保持 `consensus.json` 不动。
- 将 `candidate_tensions.json` 进一步结构化为：
  - `claim_relationships.json`
  - `application_boundaries.json`
  - `decision_rules.json`
- 在最终 `SKILL.md` 或生成报告末尾新增独立章节：

```text
## 方法论分歧与适用边界
```

该章节必须写出：

- 哪些书在回答同一问题。
- 观点关系属于 `same / complementary / contextual / tension / conflict_candidate` 中哪一类。
- 各观点适合什么场景。
- agent 遇到具体任务时应如何选择或组合。

验收标准：

- 至少 2-3 对真实 collection skill 样本被用于评估。
- 对同一知识点的不同理论，系统能输出观点关系和适用边界。
- 不再把“方法名很多”直接当作分歧。
- 不强行把有张力的观点磨平成平均建议。
- `claim_relationships.json` 和 `application_boundaries.json` 可独立检查。

### R-Phase 6: Methodology Integration Into Modules

目标：把 R-Phase 5 的边界和决策规则从“报告末尾独立章节”织入每个 modular skill。

范围：

- 为 `SkillGenerator.generate_modular_skill` 增加 collection-specific context。
- 对每个 theme/module 注入相关的：
  - `claim_relationships`
  - `application_boundaries`
  - `decision_rules`
- 让每个模块内部都能写出：
  - 默认推荐流程。
  - 情境判断。
  - 不同书的适用边界。
  - 互补观点的组合顺序。
  - 疑似冲突观点的使用警告。

验收标准：

- 用户不需要只看报告末尾，也能在具体 skill module 中看到适用边界。
- `SKILL.md` 的 router 能根据用户场景选择合适模块和路线。
- 对 `contextual` / `tension` 关系，module 中必须出现明确的选择条件。

### R-Phase 7: Collection Skill Interaction

目标：让 collection skill 不只是可下载文件，而是可以被追问、验证和修订的方法论系统。

范围：

- Collection skill chat/playground。
- 用户可以问：
  - “这条规则来自哪本书？”
  - “这两个理论为什么有张力？”
  - “如果我是创业早期，应选哪条路线？”
  - “把这个方法论改成适合大公司流程。”
- 回答必须引用：
  - source book
  - claim
  - source_refs
  - application boundary
- 支持 refine 某个观点关系或某个 decision rule，而不是每次全量重跑。

验收标准：

- 对话能引用 collection skill 的 scripts 工件，而不是只读最终 `SKILL.md`。
- 用户能围绕观点关系追问。
- 用户能修订某个关系判断，并触发局部重生成。

### R-Phase 8: Knowledge Graph

目标：在观点关系稳定后，将 collection skill 的结构化知识自然映射成图谱。

不要在 `Fallback_Theme_*` 和粗糙 tension 信号上直接做图谱。图谱应建立在 R-Phase 5/6 的稳定结构上。

节点：

```text
book
theme
claim
theory
condition
decision_rule
skill_module
```

边：

```text
derived_from
same_as
alias_of
supports
complements
contextualizes
tensions_with
conflict_candidate_with
applies_to
implemented_by
```

边语义：

- `same_as`：两个 KU / claim node 经 agent judge 判断表达同一方法、原则或观点。它用于审计归一化决策，不等同于 `claim_relationships.relationship = same` 的渲染分类。
- `alias_of`：不同术语、命名或书中表述指向同一 canonical claim / theory。
- `complements`、`contextualizes`、`tensions_with`、`conflict_candidate_with` 分别来自 R-Phase 5 的 `claim_relationships.json`。

每条 identity / relationship 边至少包含：

```text
confidence
evidence_claim_ids
source_book_ids
decided_by
created_in_run_id
```

范围：

- 新增 graph read API。
- 从 `source_kus.json`、`same_as_edges.json`、`structured_claims.json`、`claim_identity_registry.json`、`claim_relationships.json`、`application_boundaries.json`、`decision_rules.json` 派生 graph。
- 前端提供 collection graph view。
- graph 节点点击后能回到 source book / claim / skill module。

验收标准：

- 图谱能解释某个决策规则来自哪些书和观点。
- 图谱能解释为什么多个 KU / claims 被视为同一个知识点。
- 图谱能展示观点之间的互补、场景化和张力关系。
- 图谱不是装饰性可视化，而是可用于导航和验证的知识界面。

### R-Phase 9: Knowledge Asset Lifecycle

目标：把 collection 从一次性生成变成长期维护的领域知识库。

范围：

- 新书加入 collection 后增量更新。
- collection skill 版本管理。
- 使用稳定 `claim_key` 和 `same_as` / `alias_of` identity 边做版本 diff，而不是只做文本 diff。
- 比较两个版本的：
  - claims
  - relationships
  - boundaries
  - decision rules
  - final skill
- 支持导出：
  - skill package
  - domain playbook
  - SOP
  - prompt pack
  - graph data

验收标准：

- 用户可以长期维护一个领域 collection。
- 系统能解释新书加入后改变了哪些共识、分歧和决策规则。
- 系统能区分“新增知识点”“旧知识点的新别名”“旧知识点的新来源”“关系判断改变”。
- 旧版本可追溯，新版本可对比。

## 推荐实现顺序

已完成或基本完成：

1. 新增 collection 数据模型和 Alembic migration。
2. 新增 collection CRUD API。
3. 新增 collection skill package shell、pack/download。
4. 新增 `generate_collection_skill_task`，从 `book_knowledge_units` 读取书级 KU。
5. 已将单书 LLM 路径和 agent 路径产出的 KU 统一写入 `book_knowledge_units`，collection 不再依赖“最新 skill package 是否带 `extracted_kus.json`”。
6. 已实现非销毁式跨书 KU 归一化第一步：原始 KU 保留在 `source_kus.json`，embedding 相似候选关系记录在 `same_as_edges.json`，下游使用派生的 `deduped_view.json`。
7. agent skill package 会在 `scripts/extracted_kus.json` 中导出一份 KU 快照，便于审查；该快照不是 collection / KG 的 source of truth。
8. 新增 collection 创建页、详情页、生成入口、preview 页。
9. 增加运行历史、失败原因、stale/error retry。

下一阶段：

10. 执行 R-Phase 5：由后端 collection pipeline 产出观点级知识建模、claim 对齐、关系判断和适用边界。
11. 建立 collection-level identity store，持久化稳定 `claim_key`、KU/claim identity edge 和 review flags。
12. 执行 R-Phase 6：把边界和决策规则织入 modular skill。
13. 执行 R-Phase 7：collection skill chat/playground/refine。
14. 执行 R-Phase 8：从稳定观点关系派生知识图谱。
15. 执行 R-Phase 9：增量更新、版本管理和知识资产导出。

尚未实现的知识图谱范围：

- 还没有 `KnowledgeNode` / `KnowledgeEdge` 表。
- 还没有 `CollectionClaimIdentity` / `CollectionIdentityEdge` 表。
- 还没有 `/api/graph/{collection_id}`。
- 还没有图谱 UI。
- 还没有从 `same_as_edges`、`claim_relationships`、`application_boundaries` 派生 `same_as`、`alias_of`、`complements`、`contextualizes`、`tensions_with` 等图边。
- 还没有基于稳定 `claim_key` 的增量 diff 和版本对比。

## 风险与取舍

### KU 缺失风险

如果某些书还没有生成过单书 skill，可能没有可复用 KU。第一版可以选择：

- 自动补抽 KU。
- 或提示用户先生成单书 skill。

推荐自动补抽，但要把 pipeline phase 持久化，避免失败后重复消耗。

### 冲突检测质量

分歧检测很依赖 prompt 和 source metadata。第一版可以先输出“潜在分歧”，不要过度承诺强逻辑一致性。

### Skill 过大

多书综合 skill 容易变得很长。需要限制模块数，并把详细来源放到 `references/` 或 JSON scripts 中。

### 模型成本

跨书归一化、聚类、共识提炼会增加 LLM 调用。第一版应尽量复用已提取 KU，避免重新扫全文。

## 结论

Multi-book Skill Generation 是 `book2skills` 的自然扩展。它不需要第一版就引入完整知识图谱，只需要把现有单书 KU pipeline 提升到 collection 级别。

这个功能的核心差异化是：

```text
多本书 -> 跨书共识 + 保留分歧 + 场景化方法论 -> 可安装 agent skill
```

这会让 `book2skills` 从“把一本书变成 skill”进化为“把一个领域书库编译成 agent 可执行能力”。

## 采纳决策

本项目采用本文档的 collection-first 设计，而不是把 collection skill 强行塞进现有单书 `SkillPackage` 模型。

具体决策：

- 新增 collection 相关数据模型，保持单书 skill 与多书 skill 的边界清晰。
- collection skill 拥有独立的生成任务、API 和中间产物。
- 第一版必须显式包含 `CrossBookNormalizer`、`ConsensusTensionAnalyzer`、`CollectionSkillGenerator`。
- 不采用“多本书 KU 合并后直接复用现有 cluster -> skill”的简化路径，因为它容易把多书 skill 做成更大的单书摘要，无法稳定保留跨书共识与分歧。
- KU 来源优先复用每本书已有的 `extracted_kus.json` 或 `extracted_kus_partial.json`；只有缺失时才逐本书检索 Qdrant chunks 并补抽 KU。
- Qdrant 当前是每本书一个 collection，短期不改成全局 chunks collection。
- 知识图谱作为后续阶段，不进入第一版交付范围。
