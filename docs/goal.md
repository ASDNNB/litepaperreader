# LitePaperReader — 项目目标与路线图

## 最终目标

构建一个**类型安全、可溯源、可组合的数据智能管道工厂**。

```
任何原始数据
  → 通过可插拔工具转换为类型化的统一数据流 (Cell)
  → 通过可编程的 DAG 工具链提取结构化知识
  → 输出给任意大模型，回答可精确溯源到源坐标
```

## 四个不可妥协的核心

### 1. 类型安全 (Type-Safe Cell)
每种数据有明确的 ContentType（TEXT / CODE / TABLE / IMAGE / AUDIO），处理策略由类型驱动，不是黑盒。Cell 是贯穿始终的统一数据单元。

### 2. 绝对溯源 (Immutable Provenance)
任何输出都能追溯到原始文件的坐标。VirtualPurifier 的区间融合确保源文本只读，每个 Cell 携带 SourceRef（connector + resource_path + span + lineage）。

### 3. 工具可组合 (Composable DAG)
不是固定串行管道，而是可编程的有向无环图。Adapter→Splitter→Extractor→Filter→Aggregator，每条边由用户决定。同一份数据可以走不同路径。

### 4. 模型无关 (Model-Agnostic)
工具链里的每个工具可以独立选择模型大小：7B 做批量粗筛，GPT-4 做高精度提取，MiniLM 做嵌入。互不干扰，同一管道可以混合不同规模模型。

## 好方向的例子

| 场景 | 做法 | 为什么好 |
|------|------|---------|
| 10 篇论文对照分析 | PDFAdapter → SchemaExtractor → 结构化卡片 → 精确计数 | 不是 embedding 相似度，是精确的结构化提取 |
| 代码仓库理解 | GitConnector → CodeAdapter → RelationBuilder → 调用图 | 代码是 CODE ContentType，有自己的处理策略 |
| 混合数据源财报分析 | PDFAdapter + TableAdapter + HTMLAdapter → RelationBuilder → 统一 QA | 不同类型数据走不同 Adapter，结果统一进入 KnowledgePackage |
| 增量文档监控 | Watch mode 监听目录 → 文件变化自动触发管道 → 索引增量更新 | 从批处理走向实时数据流 |

## 坏方向的例子

| 场景 | 做法 | 为什么坏 |
|------|------|---------|
| 再造 RAG 聊天机器人 | 切块 → embedding → 向量检索 → LLM 回答 | 跟 LangChain/LlamaIndex 没有区别，放弃核心差异 |
| 一个大模型包办 | 整本书塞进 GPT-4 上下文 | 放弃工具链、类型安全、溯源 |
| 过度追求 Web UI | 功能堆砌但核心数据流不完整 | UI 是展示手段，不是护城河 |
| 对标 LangChain | 做 Agent、Tool calling、Chain | 定位不同，LangChain 解决"怎么调 LLM"，我们解决"怎么把数据处理成 LLM 能消费的结构化信息" |
| 只做文本 | 只支持 PDF/TXT | 浪费了 CodeAdapter、TableAdapter、WebConnector |

## 当前状态评估

| 组件 | 状态 | 说明 |
|------|------|------|
| Cell 类型系统 | ✅ 完成 | ContentType, SourceRef, StructureMeta, Relation |
| VirtualPurifier | ✅ 完成 | 区间融合算法，只读源文本 |
| SchemaRegistry | ✅ 完成 | 动态 Pydantic 模型 + YAML 加载 |
| HybridRetriever | ✅ 完成 | BM25 + RRF + 可选语义 |
| SemanticEncoder | ✅ 完成 | MiniLM + OpenAI 双后端 |
| FileSystemConnector | ✅ 完成 | 惰性 glob 扫描 |
| GitConnector | ✅ 完成 | ls-files 工作树遍历 |
| WebConnector | ✅ 完成 | HTTP + sitemap |
| HTMLAdapter | ✅ 完成 | trafilatura + readability 降级 |
| TableAdapter | ✅ 完成 | CSV/XLSX/Parquet |
| CodeAdapter | ⚠️ 骨架 | tree-sitter 后端是 fallback，缺少真正多语言支持 |
| PDFAdapter | ⚠️ 骨架 | docling 后端未充分测试 |
| Toolchain DAG | ✅ 完成 | 拓扑排序 + 串行/并行 |
| DataPipeline | ✅ 完成 | 编排器 + with_schema_extractor |
| SchemaExtractor | ✅ 完成 | 4 模式 (mock/ollama/instructor/json) |
| AnswerGenerator | ✅ 完成 | 4 模式 + 引用溯源 |
| KnowledgePackage | ✅ 完成 | StructuredCard + SummaryTree |
| Cross-document 分析 | ❌ 未开始 | RelationBuilder 是 stub |
| 真实模型集成测试 | ⚠️ 未验证 | 需要 Ollama 或 OpenAI API key |
| 增量处理/Watch 模式 | ❌ 未开始 | 目录监听 + 自动处理 |

## 下一步

优先级由核心价值决定，不是由实现难度决定：

1. **CodeAdapter 真树解析** — 让 tree-sitter 真正支持 Python/JS/TS/Rust/Go，使 CODE ContentType 名副其实
2. **Cross-document RelationBuilder** — 跨文档关联 Cell（引用、共现、时序），这是"管道工厂"区别于"单个文档工具"的关键
3. **真实模型集成测试** — 连接 Ollama 或 OpenAI，验证 SchemaExtractor + AnswerGenerator 的全链路
4. **Watch 模式** — 监听目录，文件变化自动触发管道路径

## 不做清单

- ❌ 不做独立的 RAG 聊天机器人
- ❌ 不做 LangChain 替代品
- ❌ 不在 Web UI 上过度投入
- ❌ 不做自己不能溯源的回答
- ❌ 不做只有一个模型的管道
