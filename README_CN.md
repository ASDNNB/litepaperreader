# LitePaperReader 数据流引擎

> **通用数据流智能管道** — 类型安全、可溯源、可组合的数据处理与知识提取工厂。

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-91%20passing-brightgreen.svg)](tests/)
[![CI](https://github.com/ASDNNB/litepaperreader/actions/workflows/ci.yml/badge.svg)](https://github.com/ASDNNB/litepaperreader/actions/workflows/ci.yml)

[English](README.md) | 中文

---

## 为什么选择 LitePaperReader？

传统 RAG 系统把文档当作不透明的文本块 — 盲切块、模糊嵌入、模糊匹配。你得到一个回答，但无法追溯到来源。

**LitePaperReader** 的做法不同：它把原始数据转换为类型化、可溯源的统一数据流，提取结构化信息，并给出带精确源坐标的回答。

- **类型安全的数据单元** — 每个 Cell 有明确的 ContentType（文本/代码/表格），处理策略由类型驱动。
- **绝对溯源** — 每个输出都可以追溯到源文件的行号范围，源文本只读。
- **可组合的 DAG 管道** — 工具按有向无环图编排，同一份数据可以走不同的处理路径。
- **模型无关** — 每个工具独立选择模型大小：7B 做批量筛选，GPT-4 做精确提取。

---

## 功能特性

### 数据摄入
- **多格式支持** — HTML、PDF、CSV、XLSX、Python、JavaScript、Rust、Go 等
- **源连接器** — 文件系统、Git 仓库、Web 页面
- **VirtualPurifier** — 脏数据自动标记跳过，不改动源文本

### 结构化提取
- **SchemaRegistry** — 从 YAML / Python 模板动态生成 Pydantic 模型
- **SchemaExtractor** — 4 种后端：mock（关键字）、ollama（本地）、instructor（结构约束）、json（API）
- **跨文档分析** — RelationBuilder 自动发现跨文档的关键词和引用关系

### 检索与回答
- **HybridRetriever** — BM25 词汇 + MiniLM 语义 + RRF 融合，无需外部向量数据库
- **AnswerGenerator** — 4 种后端，回答带 Cell 级引用
- **KnowledgePackage** — 结构化卡片 + 摘要树 + 溯源映射

### LLM 集成
- **MCP 服务** — 通过 Model Context Protocol 暴露 4 个工具
- **文件监控** — 目录变化自动处理并持久化到 SQLite
- **Python API & CLI** — 程序化访问所有管道阶段

### 运维
- **YAML 配置** — 单个 ``litepaper_config.yaml`` 控制管道、模型和监控
- **Docker 支持** — 开箱即用的 ``Dockerfile`` 和 ``docker-compose.yml``
- **Web 界面** — 零依赖浏览器界面，访问 ``http://localhost:8765``

---

## 快速开始

### 安装

```bash
pip install -e .
```

### 处理文档

```python
from litepaperreader.pipeline.orchestrator import DataPipeline
from litepaperreader.core.schema import SchemaRegistry, SchemaTemplate, FieldSpec
from litepaperreader.knowledge.answer import AnswerGenerator
from litepaperreader.connectors.base import ResourceRef
import asyncio

reg = SchemaRegistry()
reg.register(SchemaTemplate("paper", "学术论文", (
    FieldSpec("method", "核心方法"),
    FieldSpec("finding", "关键结果"),
)))

pipeline = DataPipeline()
pipeline.add_default_adapters()
pipeline.with_schema_extractor(reg, "paper", mode="mock")

async def run():
    kp = await pipeline.run_raw(
        ResourceRef("test", "/doc.html", content_type_hint="html"),
        b"<html><body><p>本文提出了一种新的深度学习方法，准确率达95%。</p></body></html>",
    )
    return await AnswerGenerator(mode="mock").answer("方法是什么？结果如何？", kp)

answer = asyncio.run(run())
print(answer.text)
```

### MCP 服务（大模型插件）

```bash
python mcp_server.py --db index.db --watch-dir ./docs
```

任何支持 MCP 的宿主（Codex CLI、Claude Desktop、Cursor）可以调用 4 个工具：
analyze_document / get_cell_detail / search_content / answer_question。

### Web 界面

```bash
python webui.py
# 打开 http://localhost:8765
```

---

## 安装

### 核心
```bash
pip install -e .
```
需要 Python 3.11+。

### 可选依赖
```bash
pip install -e .[all]    # 安装全部
```

### Docker
```bash
docker-compose up
```

---

## 测试

```bash
pytest tests/ -v
```

91 通过，4 跳过（需要 pyyaml / Ollama 等可选依赖）。

---

## 许可证

[MIT](LICENSE) © LitePaperReader
