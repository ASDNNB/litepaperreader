# LitePaperReader 数据流智能引擎

> **通用数据流智能管道** — 类型安全、可溯源、可组合的数据处理工厂，面向文档、代码与结构化数据。

[![版本](https://img.shields.io/badge/version-1.0.0--dev-blue?style=flat-square)](https://github.com/ASDNNB/litepaperreader/releases)
[![Python](https://img.shields.io/badge/python-3.11%2B-brightgreen?style=flat-square)](https://www.python.org/)
[![许可证](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/ASDNNB/litepaperreader/ci.yml?branch=master&style=flat-square)](https://github.com/ASDNNB/litepaperreader/actions)
[![平台](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey?style=flat-square)]()
[![MCP](https://img.shields.io/badge/MCP-ready-purple?style=flat-square)](mcp_server.py)

[English](README.md) | 中文

## 为什么选择 LitePaperReader？

现代 AI 文档处理有一个根本性缺陷：大语言模型消费非结构化文本，但真正的价值在于**结构化、可溯源的信息**。现有工具要么将原始文本直接塞入上下文窗口，要么把每个文档当作不透明的内容块。

**LitePaperReader** 弥补了这一鸿沟——它通过数据流管道将原始文档、代码和表格转换为带类型标注、可溯源的数据单元（Cell），再通过可组合的有向无环图（DAG）工具链提取结构化知识，全程模型无关。

- **类型安全（Type-Safe Cells）** — 每个数据单元携带明确的 ContentType（TEXT / CODE / TABLE / IMAGE），处理策略由类型驱动，而非启发性规则
- **绝对溯源（Absolute Provenance）** — 每个输出都能追溯到原始文件的具体坐标，拒绝黑箱提取
- **可组合 DAG（Composable DAG）** — 不是固定的线性管道。Adapter → Splitter → Extractor → Filter → Aggregator，每条边由你决定
- **模型无关（Model-Agnostic）** — 链中的每个工具可独立选择模型规模。BM25 做批量粗筛，GPT-4 做高精度提取，MiniLM 做嵌入，自由混搭

## 核心功能

### 数据管道
- **多格式输入** — HTML、PDF、CSV、代码文件、纯文本——每种格式有专属适配器，输出统一的 Cell 类型
- **DAG 工具链** — 拓扑排序的串行/并行执行图。添加、移除或重排工具无需重写管道
- **监听模式** — 监控目录文件变更，自动触发处理并增量索引

### Schema 提取
- **灵活的 Schema 定义** — 通过 Pydantic 模型或 YAML 文件定义提取模板，一次注册，跨文档复用
- **四种提取模式** — Mock（基于关键词，无需模型）、Ollama（本地大模型）、Instructor/OpenAI（云端）、JSON 模式
- **字段级控制** — 精确指定每个 Schema 字段提取什么，附带来源引用

### MCP 集成
- **MCP 服务器** — 将完整管道暴露为 MCP 工具。任何 MCP 兼容的大模型宿主（Codex CLI、Claude Desktop 等）可直接调用 analyze_document、search_content 和 answer_question
- **Cell 级引用** — 每个答案附带精确的源坐标，而非模糊引用
- **共享索引** — 监听模式与 MCP 服务器共享同一 SQLite 索引，增量更新零延迟

### 混合检索
- **BM25 + 稠密向量（可选）** — 倒数排名融合（RRF）实现最佳检索效果
- **语义编码器** — 可选 MiniLM 或 OpenAI 嵌入，用于语义搜索
- **跨文档关联** — Relation Builder 在不同文档间关联 Cell，支持交叉引用

## 截屏

| 管道架构图 | Web 界面 | MCP 连接 |
|----------|---------|---------|
| _图例制作中_ | _截屏制作中_ | _截屏制作中_ |

## 快速开始

### 一分钟体验

`ash
pip install -e .
pytest tests/ -v
`

### 处理文档

`python
from litepaperreader.pipeline.orchestrator import DataPipeline
from litepaperreader.core.schema import SchemaRegistry, SchemaTemplate, FieldSpec
from litepaperreader.connectors.base import ResourceRef
from litepaperreader.knowledge.answer import AnswerGenerator
import asyncio

# 1. 定义要提取的内容
reg = SchemaRegistry()
reg.register(SchemaTemplate("paper", "学术论文", (
    FieldSpec("method", "使用的核心方法"),
    FieldSpec("finding", "关键结果"),
)))

# 2. 构建管道
pipeline = DataPipeline()
pipeline.add_default_adapters()
pipeline.with_schema_extractor(reg, "paper", mode="mock")

# 3. 运行
async def run():
    ref = ResourceRef("fs", "paper.html", content_type_hint="html")
    with open("paper.html", "rb") as f:
        kp = await pipeline.run_raw(ref, f.read())
    gen = AnswerGenerator(mode="mock")
    answer = await gen.answer("这篇论文提出了什么方法？", kp)
    return answer

answer = asyncio.run(run())
print(answer.text)        # 带溯源的答案
print(answer.citations)   # [Citation(cell_id="...", text="...")]
`

## 安装

### 核心安装（无需外部模型）

`ash
pip install -e .
`

### 可选依赖组

| 组 | 安装命令 | 功能 |
|-----|---------|------|
| PDF | pip install -e .[pdf] | PDF 处理（docling & markitdown） |
| 嵌入 | pip install -e .[embed] | 语义搜索（sentence-transformers + scikit-learn） |
| 代码 | pip install -e .[code] | 多语言 AST 解析（tree-sitter） |
| 网页 | pip install -e .[web] | HTTP 和站点地图连接（trafilatura + httpx） |
| YAML | pip install -e .[yaml] | YAML Schema 加载 |
| **全部** | pip install -e .[all] | 以上所有功能 |

> **要求 Python 3.11+**

### 开发模式

`ash
pip install -e .[dev]
pytest tests/ -v
`

## MCP 服务器 — 大模型插件

LitePaperReader 内置 MCP 服务器，可作为任何 MCP 兼容的大模型宿主的一等插件。

`ash
python mcp_server.py
`

### 接入 Codex CLI

在 Codex CLI 配置中添加：

`json
{
  "mcp_servers": [
    {
      "name": "litepaperreader",
      "command": "python",
      "args": ["path/to/mcp_server.py"]
    }
  ]
}
`

### 接入 Claude Desktop

在 claude_desktop_config.json 中添加：

`json
{
  "mcpServers": {
    "litepaperreader": {
      "command": "python",
      "args": ["path/to/mcp_server.py"]
    }
  }
}
`

### 可用工具

| 工具 | 功能描述 |
|------|---------|
| analyze_document | 处理文档，返回带 Cell ID 的结构化卡片 |
| get_cell_detail | 深入查看 Cell 的源坐标 |
| search_content | 搜索已处理的所有文档 |
| answer_question | 回答问题，附带 Cell 级引用 |

## 架构

`
原始数据 → 源连接器 → 格式适配器 → Cell 数据流 → 工具链 DAG → 知识包 → 回答
          (文件/Git/网页) (HTML/CSV/PDF/代码) (带类型 Cell) (切分/提取/关联)(结构化卡片)(带引用)
`

`
litepaperreader/
  core/           Cell 类型、SchemaRegistry、混合检索、语义编码
  connectors/     文件系统、Git、Web 数据源连接
  adapters/       HTML、表格、代码、PDF 格式转换
  pipeline/       DAG 工具链、编排器、切分器、提取器
  knowledge/      知识包、问答生成器
mcp_server.py     MCP 协议服务器（大模型集成）
webui.py          本地 Web 面板 (http://localhost:8765)
tests/            75+ 测试用例，覆盖全模块
`

## 模型集成

LitePaperReader **无需任何大模型**即可通过 Mock 模式工作。需要真实 AI 提取能力时：

### Ollama（本地模型）

`ash
ollama pull llama3.2
`

`python
extractor = SchemaExtractor(reg, "paper",
    mode="ollama", model="llama3.2",
    api_base="http://localhost:11434")
`

### OpenAI

`ash
export OPENAI_API_KEY="sk-..."
`

`python
extractor = SchemaExtractor(reg, "paper",
    mode="instructor", model="gpt-4o-mini")
`

## 监听模式

监控目录并自动处理新增/变更文件：

`ash
python -m litepaperreader.pipeline.watcher --watch-dir ./docs --db index.db
`

MCP 服务器可从同一数据库加载：

`ash
python mcp_server.py --db index.db
`

### 支持的文件类型

| 扩展名 | 适配器 |
|--------|-------|
| .html, .htm, .txt, .md | HTMLAdapter |
| .csv, .tsv | TableAdapter |
| .py, .js, .ts, .rs, .go, .java | CodeAdapter |
| .pdf | PDFAdapter（需要 docling） |

## 常见问题

**问：需要 GPU 或 LLM API Key 吗？**
答：不需要。Mock 模式完全基于关键词提取和确定性回答运行。大模型仅用于提升提取质量，完全可选。

**问：与 LangChain / LlamaIndex 有何不同？**
答：那些框架解决"如何调用 LLM"的问题。LitePaperReader 解决"如何将原始数据转化为 LLM 可消费的结构化、可溯源信息"的问题。管道是类型安全、溯源追踪且模型无关的——不是一连串 LLM 调用。

**问：可以用自己的大模型吗？**
答：可以。LitePaperReader 完全模型无关。每个提取/问答工具都接受 mode 参数——mock、ollama、openai 或自定义。

**问：如何处理大文件？**
答：SemanticSplitter 智能分块，VirtualPurifier 确保源文本只读一次，区间融合后无重复处理。

**问：可以同时监控多个目录吗？**
答：可以。启动多个监听进程，各自指定 --db 路径，或通过 MCP 服务器的共享索引统一管理。

## 贡献指南

欢迎提交 Issue 和 PR！

1. Fork 本仓库并创建分支：git checkout -b feature/my-feature
2. 安装开发依赖：pip install -e .[dev]
3. 为你的改动编写测试
4. 运行全部测试：pytest tests/ -v
5. 提交 PR

详见 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。

## 许可证

[MIT](LICENSE) © 2026 LitePaperReader

[在 GitHub 上查看](https://github.com/ASDNNB/litepaperreader)
