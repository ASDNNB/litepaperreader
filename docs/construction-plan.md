# LitePaperReader V1.0 施工方案

**版本**: 1.0 | **基于白皮书**: whitepaper-v1.0-udf-engine.md | **日期**: 2026-06-12

---

## 总体策略

采用 **自底向上 + 可验证增量** 的策略。每个 Phase 产出可运行的代码和通过的测试，不依赖未完成的后续 Phase。

施工顺序: 数据类型层 → 核心模型 → 源连接 → 格式适配 → 加工管道 → 知识层 → 验证

---

## Phase 0: 项目骨架与核心数据类型 (1-2 天)

### 目标
建立项目目录结构、包配置、核心数据类型。

### 产出
- pyproject.toml — 构建配置与依赖声明
- core/cell.py — UDF Cell、SourceRef、ContentType、StructureMeta、Relation
- core/__init__.py — 公开 API

### 关键接口定义

`
ContentType: TEXT | CODE | TABLE | IMAGE | AUDIO | COMPOSITE

@dataclass Cell:
    id, source, content_type, body, structure, relations, metadata, embedding

@dataclass SourceRef:
    connector, resource_path, resource_checksum, span, lineage

@dataclass Relation:
    source_id, target_id, relation_type, metadata
`

### 验收标准
- Cell 可创建、可序列化 (to_dict / from_dict)
- SourceRef 支持 lineage 链
- Relation 支持类型化关联
- pytest 通过

---

## Phase 1: Core V1.0 升级 (1-2 天)

### 目标
将 V0.6 的四个核心模块升级迁移到 V1.0 命名空间。

### 产出
- core/purifier.py — VirtualPurifier (移植自 V0.6)
- core/schema.py — SchemaRegistry + SchemaTemplate (移植自 V0.6)
- core/retrieval.py — HybridRetriever (移植自 V0.6, 新增 L2 SQLite)
- core/embedding.py — SemanticEncoder 实现 (MiniLM 本地 + OpenAI 远程)

### 改动要点
- VirtualPurifier: 内部使用 Cell 的 Span，对外接口不变
- SchemaRegistry: 新增 YAML 模板加载
- HybridRetriever: 新增 SQLite FTS5 索引 (温数据)，保留 BM25 (热数据)
- SemanticEncoder: 从 Protocol 升级为实现类，支持 MiniLM / OpenAI 切换

### 验收标准
- 所有 V0.6 测试用例在新位置通过
- SchemaRegistry 可从 YAML 加载模板
- HybridRetriever 支持 L1 + L2 分层检索
- SemanticEncoder 可实际运行 (至少一种后端)

---

## Phase 2: Connectors (源连接器) (1-2 天)

### 目标
实现 Layer 0 的源发现层。

### 产出
- connectors/base.py — SourceConnector ABC + ResourceRef 构造器
- connectors/filesystem.py — FileSystemConnector (glob 扫描 + 文件读取)
- connectors/git.py — GitConnector (遍历工作树 + commit 历史)
- connectors/web.py — WebConnector (单一页面 + sitemap 扫描)
- 测试用例

### 关键设计
- 所有 scan() 返回惰性迭代器 (yield)
- ResourceRef 包含 checksum 用于缓存失效
- 支持路径过滤器 (+ include / - exclude glob)

### 验收标准
- FileSystemConnector 可递归扫描目录，支持 glob 过滤
- GitConnector 可遍历 git 仓库文件树 (不依赖 git clone)
- WebConnector 可下载页面并提取元数据
- 所有 scan 函数是惰性的 (验证: 大规模扫描不 OOM)

---

## Phase 3: Adapters (格式适配器) (2-3 天)

### 目标
实现 Layer 1 的数据格式转换层。

### 产出
- dapters/base.py — FormatAdapter ABC + AdapterRegistry
- dapters/pdf_adapter.py — PDFAdapter (docling 后端)
- dapters/html_adapter.py — HTMLAdapter (trafilatura 后端)
- dapters/table_adapter.py — TableAdapter (pandas 后端)
- dapters/code_adapter.py — CodeAdapter 骨架 (tree-sitter)
- 测试用例

### 关键设计
- AdapterRegistry 自动路由: 根据 ResourceRef.content_type 选择 Adapter
- 每个 Adapter 的 convert() 返回 Iterator[Cell]
- Cell 携带 SourceRef，包含原始偏移

### 验收标准
- PDFAdapter 可将 PDF 转换为多个 TEXT Cell + TABLE Cell
- HTMLAdapter 可从 HTML 提取正文内容
- TableAdapter 可从 CSV/XLSX 提取行级 Cell
- CodeAdapter 至少支持 Python 语言的基本解析

---

## Phase 4: Pipeline Toolchain (处理管道) (2-3 天)

### 目标
实现 Layer 2 的可编程工具 DAG。

### 产出
- pipeline/tool.py — PipelineTool ABC + ToolContext
- pipeline/toolchain.py — Toolchain (DAG 调度器)
- pipeline/splitters.py — SemanticSplitter + CodeSplitter + TableSplitter
- pipeline/extractor.py — SchemaExtractor (Instructor 集成)
- pipeline/embedders.py — EmbeddingEnricher
- pipeline/aggregators.py — HierarchicalAggregator
- pipeline/filters.py — Deduplicator + RelevanceFilter
- 测试用例

### 关键设计
- Toolchain 使用 networkx 管理 DAG
- 拓扑排序决定执行顺序
- Stream[Cell] 使用 AsyncGenerator
- 每个 Tool 有独立的 timeout + retry 配置

### DAG 执行流程
`
1. 构建 DAG (add_tool / add_edge)
2. 拓扑排序
3. 按层执行 (同一层的 Tool 可并行)
4. 流式输出
`

### 验收标准
- 可构建简单 DAG (Splitter → Extractor → Embedder)
- DAG 执行支持并行 (无依赖关系的 Tool 同时运行)
- SchemaExtractor 可通过 Instructor 调用本地/远程模型
- HierarchicalAggregator 可生成分级摘要

---

## Phase 5: Knowledge Interface (知识层) (1-2 天)

### 目标
实现 Layer 3 的 LLM 消费接口。

### 产出
- knowledge/package.py — KnowledgePackage + StructuredCard + ProvenanceMap
- knowledge/summary.py — SummaryTree 构建与查询
- knowledge/answer.py — AnswerGenerator (支持多种大模型)
- 测试用例

### 关键设计
- KnowledgePackage 从 Toolchain 输出构建
- SummaryTree 是分层结构: Cell → Section → Document
- AnswerGenerator 支持四种消费模式

### 验收标准
- KnowledgePackage 可从 Toolchain 输出构建
- SummaryTree 支持按粒度查询摘要
- AnswerGenerator 可以调用至少一种大模型 (Ollama / OpenAI)
- 回答包含 Cell 级引用

---

## Phase 6: 集成测试与端到端验证 (1-2 天)

### 目标
验证完整管道在几种典型场景下的运行。

### 测试场景
1. PDF 论文 → 结构化提取 → QA
2. HTML 网页 → 语义检索 → 问答
3. 代码仓库 → 签名提取 → 调用图
4. CSV 数据 → 表格理解 → 统计分析

### 验收标准
- 四种场景的端到端测试通过
- 所有 Cell 可追溯至原始资源坐标
- 回答包含有效引用
- 管道在 10000+ Cell 规模下稳定运行

---

## 优先级矩阵

| Phase | 价值 | 风险 | 优先级 | 原因 |
|-------|------|------|--------|------|
| Phase 0 (数据类型) | 高 | 低 | P0 | 一切依赖的基础 |
| Phase 1 (Core 升级) | 高 | 低 | P0 | 复用 V0.6 已验证的逻辑 |
| Phase 2 (Connectors) | 中 | 低 | P1 | 数据来源多样性 |
| Phase 3 (Adapters) | 高 | 中 | P1 | 核心价值: 格式无关 |
| Phase 4 (Toolchain) | 高 | 高 | P1 | 最复杂的层，DAG 调度 |
| Phase 5 (Knowledge) | 高 | 中 | P2 | 依赖 Phase 4 |
| Phase 6 (集成测试) | 高 | 中 | P2 | 验证整体 |

---

## 技术依赖清单

| 依赖 | 用途 | Phase | 可选性 |
|------|------|-------|--------|
| pydantic>=2.7 | Core 数据类型 | P0 | 必需 |
| rank-bm25>=0.2.2 | HybridRetriever | P1 | 必需 |
| networkx>=3.0 | DAG 调度 | P4 | 必需 |
| docling>=2.0 | PDF 适配器 | P3 | 可选 (可用 marker 替代) |
| tree-sitter>=0.21 | CodeAdapter | P3 | 可选 (代码阅读功能) |
| sentence-transformers | SemanticEncoder | P1 | 可选 (可退化为仅 BM25) |
| instructor>=1.0 | SchemaExtractor | P4 | 可选 (可退化为纯 JSON mode) |
| trafilatura>=1.0 | HTMLAdapter | P3 | 可选 (可用 readability) |
| httpx>=0.25 | WebConnector | P2 | 可选 |

---

## 发布标准 (V1.0-alpha)

- [ ] Phase 0-5 代码实现完成
- [ ] 核心模块单元测试覆盖率 > 85%
- [ ] 端到端场景 ≥ 3 种通过
- [ ] 1000 Cell 规模管道执行无 OOM
- [ ] 白皮书与代码一致
- [ ] docs/ 下包含白皮书 + 施工方案

---

*施工方案版本 1.0 — 对应 LitePaperReader V1.0 UDF Engine*
