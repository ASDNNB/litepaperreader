# LitePaperReader V1.0 — 统一数据流处理引擎 (UDF Engine) 白皮书

**版本**: 1.0 | **状态**: 架构设计阶段 | **前身**: LitePaperReader V0.6

---

## 一、项目核心理念

LitePaperReader V1.0 从一个"本地论文阅读理解中间件"演进为 **通用数据流智能处理引擎 (Universal Data Flow Intelligence Engine)**。

核心理念可以概括为三句话：

1. **任何数据都可以被工具转化为统一的数据流** — 无论输入是 PDF、代码仓库、网页、数据库还是音视频，通过 Format Adapter 层转换为同一种中间表示
2. **对数据流进行工具链式加工** — 切分、提取、增强、过滤、聚合，每一步是一个独立工具，可任意组合成 DAG
3. **将加工后的知识输出给大模型** — 大模型看到的不是原始文本切片，而是经过压缩、结构化、增强后的知识包

这就是你提出的 **"工具转换为特定数据流 → 对信息流提取 → 输出至大模型"** 架构的完整实现。

### 与 V0.6 的关键区别

| 维度 | V0.6 (Paper Reader) | V1.0 (UDF Engine) |
|------|-------------------|-------------------|
| 输入范围 | PDF / Doc 文档 | 任意来源 (文件、代码、网页、DB、音视频) |
| 处理单位 | TextChunk (文本切片) | Cell (带类型/结构/关联的统一数据单元) |
| 处理管道 | 固定串行: Convert → Purify → Chunk → Extract | 可编程 DAG: Connector → Adapter → Tool[ ] → Knowledge |
| 模型依赖 | 限定 7B/8B 小模型 | 每层工具可独立选择模型 (小模型批量、大模型高精度) |
| 规模适应 | 单文档 (<200 页) | 流式处理，无上限 (惰性迭代 + 分片 + checkpoint) |
| 输出形式 | 字段提取 + 引用片段 | KnowledgePackage (结构化数据 + 分级摘要 + 可检索索引) |

---

## 二、系统分层架构

系统由四层构成，数据从源头到知识端单向流动：

- **Layer 0: Source Connectors** — 发现与读取原始资源 (FileSystem, Git, Web, DB, S3, Archive)
- **Layer 1: Format Adapters** — 统一数据流转换层，将任意原始数据转换为 UDF Cell 流
- **Layer 2: Processing Toolchain** — 数据加工工具 DAG，每个 Tool 独立可选模型
- **Layer 3: Knowledge Interface** — LLM 消费接口，提供结构化卡片、分级摘要、可检索索引

---

## 三、Layer 0: Source Connectors (源连接器)

### 3.1 统一接口

每个 Connector 实现三个核心方法：
- scan(path) → Iterator[ResourceRef] — 惰性发现资源
- ead(ref) → RawResource — 读取原始内容
- metadata(ref) → ResourceMeta — 资源元数据

### 3.2 预置连接器

| 连接器 | 输入 | scan 产出 | 大规模保障 |
|--------|------|----------|-----------|
| FileSystemConnector | 本地路径/glob | 文件迭代器 | 惰性扫描，不加载全部 |
| GitConnector | repo URL / 本地路径 | 文件树 + commit 历史 | shallow clone + 按需 checkout |
| WebConnector | URL / sitemap | 页面迭代器 | 异步并发 + 限速 |
| DatabaseConnector | 连接串 + 查询 | 行迭代器 | 游标分批读取 |
| ArchiveConnector | .zip/.tar | 条目迭代器 | 流式解压 |

### 3.3 关键设计

- scan() 是惰性迭代器，支持流式消费。百万级资源也可遍历，不会 OOM
- ResourceRef 携带溯源路径，确保每个 Cell 都可追溯
- 连接器无状态，可安全并行

---

## 四、Layer 1: Format Adapters (格式适配器)

这是你提出的 **"工具转换"** 层的实现。每个 Adapter 是一个独立的转换工具，将原始字节转换为统一的 Cell 流。

### 4.1 统一接口

`python
class FormatAdapter(ABC):
    def can_handle(self, resource: ResourceRef) -> bool
    def convert(self, resource: RawResource) -> Iterator[Cell]
`

### 4.2 预置适配器

| 适配器 | 核心依赖 | 产出 Cell 类型 | 模型使用 |
|--------|---------|---------------|---------|
| PDFAdapter | docling / marker | TEXT, TABLE | 不需要模型 (纯解析) |
| CodeAdapter | tree-sitter | CODE (函数/类/模块) | 可选: LLM 生成 docstring 摘要 |
| HTMLAdapter | readability + trafilatura | TEXT, LINK | 不需要模型 |
| TableAdapter | pandas | TABLE (含 schema) | 可选: LLM 理解列语义 |
| ImageAdapter | tesseract / GPT-4o | TEXT | 可选: 视觉模型 OCR |
| AudioAdapter | whisper | TEXT (分段转录) | 语音模型必选 |

### 4.3 大规模设计要点

- **流式转换**: convert() 返回 Iterator[Cell]，不需要全部加载到内存
- **异构运行时**: 不同 Adapter 可跑在不同进程/机器上
- **Cell 独立性**: 每个 Cell 包含完整溯源信息，可独立消费

---

## 五、UDF Cell — 统一数据流单元

这是整个架构的 **核心数据类型**，是所有数据经过 Adapter 后的统一形态。

`python
@dataclass
class Cell:
    id: str                    # 全局唯一 ID (含来源标识)
    source: SourceRef          # 溯源指针 {connector, resource, span}
    content_type: ContentType  # TEXT | CODE | TABLE | IMAGE | AUDIO | COMPOSITE
    body: str | bytes          # 标准化主体内容
    structure: StructureMeta   # 结构元数据 (层级、AST、schema)
    relations: list[Relation]  # Cell 间关系 (父子、引用、依赖)
    metadata: dict             # 领域元数据
    embedding: NDArray | None  # 可选: 语义嵌入
`

### 5.1 ContentType 驱动处理策略

Cell 的 content_type 决定了 Pipeline 层如何处理它：

| ContentType | 默认 Splitter | 默认 Extractor | 嵌入模型 |
|-------------|---------------|----------------|---------|
| TEXT | SemanticSplitter (段落边界) | SchemaExtractor (Instructor) | MiniLM / bge |
| CODE | CodeSplitter (tree-sitter AST) | SignatureExtractor | CodeBERT / starencoder |
| TABLE | TableSplitter (行/列边界) | SchemaExtractor (列语义) | table-embedding |
| IMAGE | 无 (单 Cell) | VisionExtractor | CLIP |
| AUDIO | 时间边界切分 | TranscriptExtractor | whisper-embedding |

### 5.2 溯源链

每个 Cell 携带 SourceRef，包含 connector 名称、资源路径、内容哈希、偏移范围和处理链。这使得：
- 回答可以精确引用 [Cell:abc123:docs/main.py:42-56]
- 支持增量更新 (resource_checksum 变化时重建)
- 消费端可以按需回调获取原始数据

---

## 六、Layer 2: Processing Toolchain (处理工具链)

### 6.1 从串行管道到可编程 DAG

V0.6 的固定管道被替换为可配置的工具 DAG。

`python
class PipelineTool(ABC):
    name: str
    input_types: set[ContentType]
    output_type: ContentType
    async def process(self, cells: Stream[Cell], ctx: ToolContext) -> Stream[Cell]

class Toolchain:
    dag: nx.DiGraph  # 有向无环图
    async def run(self, input: Stream[Cell]) -> Stream[Cell]
`

### 6.2 内置工具

**分裂器**: SemanticSplitter (段落边界)、CodeSplitter (tree-sitter AST)、TableSplitter、TokenSplitter

**提取器**: SchemaExtractor (Instructor + 动态 Pydantic, 可选 7B/8B 或 GPT-4)、SignatureExtractor (AST)、VisionExtractor、KeywordExtractor

**增强器**: EmbeddingEnricher (MiniLM/OpenAI)、SummaryEnricher、RelationBuilder

**过滤聚合**: Deduplicator、RelevanceFilter、HierarchicalAggregator、CrossEncoderReranker

### 6.3 DAG 组合示例

论文阅读理解:
`
PDFAdapter → SemanticSplitter → SchemaExtractor(7B) → EmbeddingEnricher → HybridRetriever
`

代码仓库分析:
`
GitConnector → CodeAdapter → CodeSplitter → SignatureExtractor → RelationBuilder → SummaryAggregator(GPT-4)
`

混合数据分析:
`
PDFAdapter → SemanticSplitter ─→ SchemaExtractor(7B)
                                  ↓           ↓
TableAdapter ──────────────────→ RelationBuilder → SummaryAggregator(GPT-4)
                                  ↑
WebConnector → HTMLAdapter → SemanticSplitter → KeywordExtractor
`

### 6.4 大规模保障

- **流式执行**: 所有 Tool 处理 Stream[Cell]，不要求全量数据
- **Per-Tool 并行**: DAG 中无依赖的 Tool 可并行执行
- **Batch 处理**: 通过 batch() 将流分组，适配模型推理批次大小
- **断点续传**: 每个 batch 完成后写 checkpoint，重跑时跳过已完成
- **退化路径**: 任何 Tool 失效时输出降级日志 + 跳过

---

## 七、Layer 3: Knowledge Interface (知识接口)

这是 **"输出至大模型"** 的实现层。大模型不直接看原始 Cell，而是看加工后的 KnowledgePackage。

`python
@dataclass
class KnowledgePackage:
    cards: list[StructuredCard]       # 结构化提取卡片
    summary_tree: SummaryTree         # 分级摘要树 (Cell→Section→Document)
    index: RetrievalIndex             # 可检索索引 (BM25 + 语义)
    provenance: ProvenanceMap         # 所有卡片→来源 Cell 的映射
`

### 7.1 四种 LLM 消费模式

| 模式 | 场景 | 传输内容 |
|------|------|---------|
| 直接注入 | 宏观理解、文档总结 | cards.to_json() + 根摘要 |
| 按需检索 | 精确问答、事实核查 | HybridRetriever(query) → top-k Cell |
| 工具回调 | 深度追问、代码审查 | LLM 通过 tool 获取完整 Cell 体 |
| 流式扫描 | 批量数据质量检查 | Cell 流逐个喂给 LLM |

### 7.2 AnswerGenerator

`python
class AnswerGenerator:
    def __init__(self, model: str = "gpt-4o"):  # 不限大小不限提供商
        ...

    async def answer(self, question, knowledge, mode="auto") → Answer:
        # 返回带引用的答案
`

Answer 格式:
`
{
  "answer": "论文提出了一种...",
  "citations": [
    {"cell_id": "cell-0032", "span": "42-56", "text": "核心方法是..."},
    {"cell_id": "cell-0087", "span": "12-34", "text": "实验结果表明..."}
  ],
  "confidence": 0.92
}
`

---

## 八、四大工程壁垒 (V1.0 升级版)

### 壁垒 1: 强类型统一数据流 (Type-Safe UDF)
V0.6 的 SchemaRegistry + create_model 升级为 UDF Cell 的类型系统。每个 Cell 的 content_type 驱动其处理策略，StructureMeta 提供结构感知。

### 壁垒 2: 绝对溯源的 Cell 指针 (Immutable Cell Pointers)
VirtualPurifier 保留。SourceRef 增加 lineage 链，支持多级溯源。所有输出都可通过 CellRef 追溯到原始坐标。

### 壁垒 3: 结构化工具 DAG (Graph over Pipeline)
放弃固定串行管道。类型安全的 Tool 接口，DAG 拓扑排序自动推导执行顺序。支持分支、合并、并行、降级。

### 壁垒 4: 混合检索 + 分级摘要 (Hybrid Retrieval + Hierarchical Summary)
L1: BM25 in-memory (热数据)、L2: SQLite FTS5 (温数据百万级)。分级摘要树自动选择检索层级。

---

## 九、大规模数据处理保障

- **流式处理**: 全管道以 Stream 为基本单位
- **惰性嵌入与分层缓存**: L1 内存 → L2 SQLite/mmap → L3 远程存储
- **分片并行**: batch(256) + ThreadPoolExecutor
- **Checkpoint 容错**: run_id + completed_cells + failed_cells
- **退化与熔断**: 超时/重试 → 跳过 → 日志 → fallback

---

## 十、软件工程阅读的扩展路径

UDF 架构天然支持代码阅读，不需要另起项目：

`
GitConnector → CodeAdapter(tree-sitter) → CodeSplitter
    → SignatureExtractor → RelationBuilder
    → SummaryAggregator → KnowledgePackage
`

需要新增的组件: CodeAdapter、CodeSplitter、SignatureExtractor、RelationBuilder(CODE)、DiffAdapter

架构兼容点: Cell 的 content_type=CODE 驱动专用策略，StructureMeta 存 AST/符号表，relations 承载引用关系。

---

## 十一、与 V0.6 的兼容性

| V0.6 模块 | V1.0 位置 | 改动量 |
|-----------|----------|--------|
| VirtualPurifier | core/purifier.py | 保留，Cell 内部使用 |
| SchemaRegistry | core/schema.py | 保留，Extractor 依赖 |
| StructureAwareChunker | pipeline/splitters.py | 保留，成为 SemanticSplitter 实现之一 |
| HybridRetriever | core/retrieval.py | 保留，成为索引引擎 |

业务逻辑无需重写，只需为新层编写适配代码。

---

*LitePaperReader V1.0 — 从论文阅读器到通用数据流处理引擎*
*2026-06-12*
