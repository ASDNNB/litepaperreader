# SchemaExtractor — 结构化提取使用指南

SchemaExtractor 是 LitePaperReader V1.0 的核心提取引擎，支持四种后端模式。

## 四种模式

| 模式 | 标签 | 适用场景 | 依赖 |
|------|------|---------|------|
| Mock | `mode="mock"` | 测试、开发、无需真实模型 | 无 |
| Ollama | `mode="ollama"` | 本地部署 (Llama/Qwen 等) | `requests` |
| Instructor | `mode="instructor"` | 高精度结构化提取 | `instructor` + `openai` |
| JSON | `mode="json"` | OpenAI 兼容 API 通用模式 | `openai` |

## 快速开始 (Mock 模式)

```python
from litepaperreader.core.schema import SchemaRegistry, SchemaTemplate, FieldSpec
from litepaperreader.pipeline.extractor import SchemaExtractor
from litepaperreader.core.cell import Cell, ContentType, SourceRef
import asyncio, json

# 1. 定义 Schema
reg = SchemaRegistry()
reg.register(SchemaTemplate(
    template_id="paper",
    description="Academic paper",
    fields=(
        FieldSpec(name="title", description="The paper title"),
        FieldSpec(name="method", description="Core method used"),
        FieldSpec(name="result", description="Key experimental result"),
    ),
))

# 2. 创建提取器 (Mock 模式, 不需要模型)
extractor = SchemaExtractor(reg, template_id="paper", mode="mock")

# 3. 提取
ref = SourceRef(connector="test", resource_path="doc.txt", resource_checksum="abc")
cell = Cell(id="doc1", source=ref, content_type=ContentType.TEXT,
            body="This paper proposes a novel method for semantic segmentation.")

async def run():
    async def input_cells():
        yield cell
    async for c in extractor.process(input_cells(), None):
        return json.loads(c.body)

result = asyncio.run(run())
print(result)
# -> {"title": "Mock[paper]", "method": "Mock[method]", "result": null}
```

## 使用 DataPipeline (Mock 模式)

```python
from litepaperreader.pipeline.orchestrator import DataPipeline
from litepaperreader.connectors.base import ResourceRef
from litepaperreader.core.schema import SchemaRegistry, SchemaTemplate, FieldSpec
import asyncio

reg = SchemaRegistry()
reg.register(SchemaTemplate(template_id="paper", description="Paper", fields=(
    FieldSpec(name="title", description="Paper title"),
    FieldSpec(name="method", description="Method used"),
)))

pipeline = DataPipeline()
pipeline.add_default_adapters()
pipeline.with_schema_extractor(reg, template_id="paper", mode="mock")

html = b"<html><body><h1>New Method</h1><p>A novel method for ML.</p></body></html>"
ref = ResourceRef(connector="test", resource_path="/doc.html", content_type_hint="html")

kp = asyncio.run(pipeline.run_raw(ref, html))
print(kp.metadata)  # -> {"num_cells": ..., "num_cards": ..., ...}
```

## Ollama 本地部署

```python
# 1. 安装依赖: pip install requests
# 2. 启动 Ollama: ollama pull llama3.2 && ollama serve

extractor = SchemaExtractor(
    reg, template_id="paper",
    mode="ollama",
    model="llama3.2",
    api_base="http://localhost:11434",
)
```

## Instructor + OpenAI

```bash
pip install instructor openai

# 设置 API Key
$env:OPENAI_API_KEY = "sk-..."
```

```python
extractor = SchemaExtractor(
    reg, template_id="paper",
    mode="instructor",
    model="gpt-4o-mini",
    api_key="sk-...",
)

# 或通过 DataPipeline
pipeline.with_schema_extractor(
    reg, template_id="paper",
    mode="instructor", model="gpt-4o-mini",
    api_key="sk-...",
)
```

## JSON 模式 (OpenAI 兼容)

```python
extractor = SchemaExtractor(
    reg, template_id="paper",
    mode="json",
    model="gpt-4o-mini",
    api_key="sk-...",
)
```

## 提取结果

提取结果包含在 KnowledgePackage 的 `cards` 字段中:

```python
for card in kp.cards:
    print(f"Schema: {card.schema_id}")
    print(f"Fields: {card.fields}")
    print(f"Source: {card.source_cell_id}")
    print(f"Confidence: {card.confidence}")
```
