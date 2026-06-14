"""AnswerGenerator — multi-backend QA engine with grounded citations."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from litepaperreader.knowledge.package import KnowledgePackage, StructuredCard

logger = logging.getLogger(__name__)


@dataclass
class Citation:
    cell_id: str
    span_text: str | None = None
    text: str | None = None


@dataclass
class Answer:
    text: str
    citations: list[Citation] = field(default_factory=list)
    confidence: float = 1.0
    consumption_mode: str = "auto"
    metadata: dict[str, Any] = field(default_factory=dict)


class AnswerGenerator:
    """Generate grounded answers from KnowledgePackage content.

    Supports four backends:

    ======  ========================================  =================
    Mode    Description                               Dependencies
    ======  ========================================  =================
    mock    Keyword-based mock for testing             none
    openai  OpenAI / OpenAI-compatible API             openai
    claude  Anthropic Claude API                      anthropic
    ollama  Local Ollama (OpenAI-compatible API)       requests
    ======  ========================================  =================

    Consumption modes:

    ========  ============================================================
    Mode      Description
    ========  ============================================================
    inject    Full structured context sent in one LLM call
    retrieve  Use HybridRetriever to find top-k relevant cells first
    auto      Pick inject for small knowledge, retrieve for large
    ========  ============================================================

    Usage::

        gen = AnswerGenerator(mode="mock")
        answer = await gen.answer(
            "What method does the paper propose?",
            knowledge_package,
        )
        print(answer.text)       # "Based on 2 relevant card(s): ..."
        print(answer.citations)  # [Citation(cell_id="...", ...)]
    """

    MODE_MOCK = "mock"
    MODE_OPENAI = "openai"
    MODE_CLAUDE = "claude"
    MODE_OLLAMA = "ollama"
    MODE_DEEPSEEK = "deepseek"

    def __init__(
        self,
        model: str = "gpt-4o",
        mode: str = "mock",
        api_key: str | None = None,
        api_base: str | None = None,
        max_context_chars: int = 8000,
    ):
        self._model = model
        self._mode = mode
        self._api_key = api_key
        self._api_base = api_base
        self._max_context_chars = max_context_chars

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def answer(
        self,
        question: str,
        knowledge: KnowledgePackage,
        mode: Literal["auto", "inject", "retrieve"] = "auto",
    ) -> Answer:
        """Answer a question grounded in the given KnowledgePackage."""
        resolved_mode = self._resolve_mode(mode, knowledge)
        context = self._build_context(knowledge, resolved_mode)

        if self._mode == self.MODE_MOCK:
            return self._answer_mock(question, context, knowledge, resolved_mode)
        elif self._mode == self.MODE_OPENAI:
            return await self._answer_openai(question, context, knowledge, resolved_mode)
        elif self._mode == self.MODE_CLAUDE:
            return await self._answer_claude(question, context, knowledge, resolved_mode)
        elif self._mode == self.MODE_OLLAMA:
            return await self._answer_ollama(question, context, knowledge, resolved_mode)
        elif self._mode == self.MODE_DEEPSEEK:
            return await self._answer_deepseek(question, context, knowledge, resolved_mode)
        else:
            raise ValueError(f"Unknown answer generator mode: {self._mode}")

    # ------------------------------------------------------------------
    # Context building
    # ------------------------------------------------------------------

    def _resolve_mode(self, mode: str, knowledge: KnowledgePackage) -> str:
        if mode != "auto":
            return mode
        total_chars = sum(
            len(str(v)) for c in knowledge.cards for v in c.fields.values() if v
        )
        return "inject" if total_chars < self._max_context_chars else "retrieve"

    def _build_context(self, knowledge: KnowledgePackage, mode: str) -> str:
        parts: list[str] = []

        # Add summary
        if knowledge.summary_tree and knowledge.summary_tree.summary:
            parts.append(f"[Document Summary]\n{knowledge.summary_tree.summary}\n")

        # Add structured cards
        if knowledge.cards:
            card_lines: list[str] = []
            for i, card in enumerate(knowledge.cards[:20]):
                fields = {k: v for k, v in card.fields.items() if v is not None}
                if fields:
                    fields_str = "; ".join(f"{k}: {v}" for k, v in fields.items())
                    card_lines.append(f"  [{i}] ({card.schema_id}) cell={card.source_cell_id}: {fields_str}")
            if card_lines:
                parts.append("[Extracted Information]\n" + "\n".join(card_lines) + "\n")

        context = "\n".join(parts)
        if len(context) > self._max_context_chars:
            context = context[:self._max_context_chars] + "\n... (truncated)"
        return context

    # ------------------------------------------------------------------
    # Mock mode
    # ------------------------------------------------------------------

    def _answer_mock(
        self, question: str, context: str, knowledge: KnowledgePackage, mode: str
    ) -> Answer:
        """Mock mode: keyword-based answer with proper Cell citations.

        This is deterministic and testable — no model needed.
        """
        q_lower = question.lower()
        q_words = {w for w in q_lower.split() if len(w) > 3}
        citations: list[Citation] = []
        matched_fields: list[str] = []

        for card in knowledge.cards:
            for field_name, field_value in card.fields.items():
                if field_value is None:
                    continue
                fv_lower = str(field_value).lower()
                # Check if any question keyword appears in the field value
                matching_words = q_words & set(fv_lower.split())
                if matching_words:
                    citations.append(Citation(
                        cell_id=card.source_cell_id,
                        span_text=card.source_ref.span if card.source_ref else None,
                        text=str(field_value)[:200],
                    ))
                    matched_fields.append(f"{field_name}={field_value}")
                    break  # one citation per card

        if citations:
            summary = (
                f"Based on {len(citations)} relevant card(s) from "
                f"{knowledge.metadata.get('resources', 1)} resource(s): "
            )
            for c in citations[:3]:
                summary += f"[Cell:{c.cell_id}] "
            text = (
                f"{summary}\n\n"
                f"Relevant extractions: {'; '.join(matched_fields[:5])}"
            )
        else:
            total = knowledge.metadata.get("num_cells", 0)
            text = (
                f"I found {len(knowledge.cards)} extraction card(s) from {total} total cells "
                f"but none directly matched your question. "
                f"Try rephrasing or ask about: "
                + "; ".join(
                    f"{k}: {v}" for c in knowledge.cards[:3]
                    for k, v in c.fields.items() if v
                )
            )

        return Answer(
            text=text,
            citations=citations[:5],
            confidence=0.85 if citations else 0.3,
            consumption_mode=mode,
            metadata={"num_cards": len(knowledge.cards), "num_citations": len(citations)},
        )

    # ------------------------------------------------------------------
    # OpenAI mode
    # ------------------------------------------------------------------

    async def _answer_openai(
        self, question: str, context: str, knowledge: KnowledgePackage, mode: str
    ) -> Answer:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self._api_key, base_url=self._api_base)
            resp = client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a precise document analyst. Answer the question "
                            "based ONLY on the provided context. "
                            "Cite sources using [Cell:cell_id] notation. "
                            "If the context doesn't contain enough information, say so."
                        ),
                    },
                    {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
                ],
            )
            text = resp.choices[0].message.content or ""
        except ImportError:
            logger.warning("openai not installed, falling back to mock")
            return self._answer_mock(question, context, knowledge, mode)
        except Exception as e:
            logger.warning("OpenAI API error: %s", e)
            text = f"Error calling OpenAI API: {e}"

        citations = []
        for card in knowledge.cards[:5]:
            citations.append(Citation(cell_id=card.source_cell_id))
        return Answer(
            text=text,
            citations=citations,
            confidence=0.9,
            consumption_mode=mode,
        )


    # ------------------------------------------------------------------
    # DeepSeek mode (OpenAI-compatible API)
    # ------------------------------------------------------------------

    async def _answer_deepseek(
        self, question: str, context: str, knowledge: KnowledgePackage, mode: str
    ) -> Answer:
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=self._api_key,
                base_url=self._api_base or "https://api.deepseek.com/v1",
            )
            model = self._model if self._model != "gpt-4o" else "deepseek-chat"
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a precise document analyst. Answer the question "
                            "based ONLY on the provided context. "
                            "Cite sources using [Cell:cell_id] notation. "
                            "If the context doesn\'t contain enough information, say so."
                        ),
                    },
                    {"role": "user", "content": "Context:\n" + context + "\n\nQuestion: " + question},
                ],
                temperature=0.0,
            )
            text = resp.choices[0].message.content or ""
        except ImportError:
            logger.warning("openai not installed, falling back to mock")
            return self._answer_mock(question, context, knowledge, mode)
        except Exception as e:
            logger.warning("DeepSeek API error: %s", e)
            text = "Error calling DeepSeek API: " + str(e)

        citations = [Citation(cell_id=card.source_cell_id) for card in knowledge.cards[:5]]
        return Answer(
            text=text,
            citations=citations,
            confidence=0.9,
            consumption_mode=mode,
        )

    # ------------------------------------------------------------------
    # Claude mode
    # ------------------------------------------------------------------

    async def _answer_claude(
        self, question: str, context: str, knowledge: KnowledgePackage, mode: str
    ) -> Answer:
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=self._api_key)
            resp = client.messages.create(
                model=self._model,
                max_tokens=4096,
                system="You are a precise document analyst. Answer based ONLY on the context.",
                messages=[
                    {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
                ],
            )
            text = resp.content[0].text if resp.content else ""
        except ImportError:
            logger.warning("anthropic not installed, falling back to mock")
            return self._answer_mock(question, context, knowledge, mode)
        except Exception as e:
            logger.warning("Claude API error: %s", e)
            text = f"Error calling Claude API: {e}"

        citations = [Citation(cell_id=card.source_cell_id) for card in knowledge.cards[:5]]
        return Answer(text=text, citations=citations, confidence=0.9, consumption_mode=mode)

    # ------------------------------------------------------------------
    # Ollama mode (OpenAI-compatible API)
    # ------------------------------------------------------------------

    async def _answer_ollama(
        self, question: str, context: str, knowledge: KnowledgePackage, mode: str
    ) -> Answer:
        try:
            import requests as sync_requests
            base = (self._api_base or "http://localhost:11434").rstrip("/")
            resp = sync_requests.post(
                f"{base}/api/chat",
                json={
                    "model": self._model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "Answer based ONLY on the provided context. Cite [Cell:id].",
                        },
                        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.0},
                },
                timeout=120,
            )
            resp.raise_for_status()
            text = resp.json()["message"]["content"]
        except ImportError:
            logger.warning("requests not installed, falling back to mock")
            return self._answer_mock(question, context, knowledge, mode)
        except Exception as e:
            logger.warning("Ollama API error: %s", e)
            text = f"Error calling Ollama API: {e}"

        citations = [Citation(cell_id=card.source_cell_id) for card in knowledge.cards[:5]]
        return Answer(text=text, citations=citations, confidence=0.85, consumption_mode=mode)
