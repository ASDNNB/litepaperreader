"""Enhanced SchemaExtractor with mock, ollama, instructor, and JSON modes."""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from litepaperreader.core.cell import Cell, ContentType
from litepaperreader.core.schema import SchemaRegistry, SchemaTemplate
from litepaperreader.pipeline.tool import PipelineTool, ToolContext

logger = logging.getLogger(__name__)

DEEPSEEK_BASE = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"


class SchemaExtractor(PipelineTool):
    """Extract structured fields from TEXT/TABLE Cells.

    Supports four backends:

    ========  ==========================================  ====================
    Mode      Description                                  Dependencies
    ========  ==========================================  ====================
    mock      Rule-based mock for testing                  none
    ollama    Local Ollama (OpenAI-compatible API)         requests
    instructor  Instructor-constrained structured output   instructor + openai
    json      OpenAI JSON mode                             openai
    ========  ==========================================  ====================

    Usage::

        reg = SchemaRegistry()
        reg.register(SchemaTemplate(
            template_id="paper",
            description="Academic paper",
            fields=(
                FieldSpec(name="title", description="Paper title"),
                FieldSpec(name="method", description="Core method"),
            ),
        ))

        # Mock mode (testing, no model needed)
        extractor = SchemaExtractor(reg, template_id="paper", mode="mock")

        # Ollama mode (local)
        extractor = SchemaExtractor(reg, template_id="paper",
                                     mode="ollama", model="llama3",
                                     api_base="http://localhost:11434")

        # Instructor mode (remote)
        extractor = SchemaExtractor(reg, template_id="paper",
                                     mode="instructor", model="gpt-4o-mini",
                                     api_key="sk-...")
    """

    name = "schema_extractor"
    input_types = {ContentType.TEXT, ContentType.TABLE}
    output_type = ContentType.TEXT

    MODE_MOCK = "mock"
    MODE_OLLAMA = "ollama"
    MODE_INSTRUCTOR = "instructor"
    MODE_JSON = "json"
    MODE_DEEPSEEK = "deepseek"

    def __init__(
        self,
        schema_registry: SchemaRegistry,
        template_id: str,
        model: str = "gpt-4o-mini",
        api_base: str | None = None,
        api_key: str | None = None,
        mode: str = "mock",
    ):
        self._registry = schema_registry
        self._template_id = template_id
        self._model = model
        self._api_base = api_base
        self._api_key = api_key
        self._mode = mode
        self._pydantic_model = schema_registry.create_model_for(template_id)

    async def process(self, cells: AsyncIterator[Cell], ctx: ToolContext) -> AsyncIterator[Cell]:
        async for cell in cells:
            text = cell.body if isinstance(cell.body, str) else ""
            if not text.strip():
                yield cell
                continue
            try:
                extracted = await self._extract(text)
                yield Cell(
                    id=f"{cell.id}:extracted",
                    source=cell.source,
                    content_type=ContentType.TEXT,
                    body=json.dumps(extracted, ensure_ascii=False),
                    structure=cell.structure,
                    metadata={
                        "schema": self._template_id,
                        "extraction_model": self._model,
                        "extraction_mode": self._mode,
                        "type": "extraction",
                    },
                )
            except Exception as e:
                logger.warning("Extraction failed for %s: %s", cell.id, e)
                yield cell

    async def _extract(self, text: str) -> dict[str, Any]:
        if self._mode == self.MODE_MOCK:
            return self._extract_mock(text)
        elif self._mode == self.MODE_OLLAMA:
            return await self._extract_ollama(text)
        elif self._mode == self.MODE_DEEPSEEK:
            return await self._extract_deepseek(text)
        elif self._mode == self.MODE_INSTRUCTOR:
            return await self._extract_with_instructor(text)
        else:
            return await self._extract_json_mode(text)

    # ------------------------------------------------------------------
    # Mock mode -- deterministic testing without any model
    # ------------------------------------------------------------------

    def _extract_mock(self, text: str) -> dict[str, Any]:
        """Mock extraction using keyword matching against field descriptions.

        Finds the first significant word in each field's description that
        appears in the input text. This makes mock results predictable and
        verifiable, not random.
        """
        text_lower = text.lower()
        result: dict[str, Any] = {}
        for field_name, field_info in self._pydantic_model.model_fields.items():
            desc = (field_info.description or "").lower()
            found: str | None = None
            for word in desc.split():
                word = word.strip(".,;:!?()[]")
                if len(word) > 3 and word in text_lower:
                    found = word
                    break
            result[field_name] = f"Mock[{found}]" if found else None
        return result

    # ------------------------------------------------------------------
    # Ollama mode -- local models via OpenAI-compatible API
    # ------------------------------------------------------------------

    async def _extract_ollama(self, text: str) -> dict[str, Any]:
        import requests as sync_requests
        base = (self._api_base or "http://localhost:11434").rstrip("/")
        schema = self._pydantic_model.model_json_schema()
        prompt = (
            'You are a structured data extractor. '
            'Return ONLY valid JSON matching the provided schema. '
            'Set fields to null if the information is not present in the text.'
        )
        user_msg = (
            f"Schema: {json.dumps(schema, ensure_ascii=False)}\n\n"
            f"Text:\n{text[:3000]}"
        )
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_msg},
            ],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.0},
        }
        resp = sync_requests.post(
            f"{base}/api/chat",
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
        return json.loads(content)


    # ------------------------------------------------------------------
    # DeepSeek mode -- OpenAI-compatible API at api.deepseek.com
    # ------------------------------------------------------------------

    async def _extract_deepseek(self, text: str) -> dict[str, Any]:
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=self._api_key,
                base_url=self._api_base or DEEPSEEK_BASE,
            )
            model = self._model if self._model != "gpt-4o-mini" else DEEPSEEK_MODEL
            schema = self._pydantic_model.model_json_schema()
            prompt = (
                "You are a precise structured data extractor. "
                "Extract the requested fields from the text below. "
                "Return ONLY valid JSON. Set fields to null if missing."
            )
            resp = client.chat.completions.create(
                model=model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": prompt + chr(10)*2 + "Expected schema:" + chr(10) + json.dumps(schema)},
                    {"role": "user", "content": text[:8000]},
                ],
                temperature=0.0,
            )
            content_resp = resp.choices[0].message.content
            content_resp = resp.choices[0].message.content
            if content_resp:
                return json.loads(content_resp)
            return {}
        except ImportError:
            logger.warning("openai not installed, falling back to mock")
            return self._extract_mock(text)
        except Exception as e:
            logger.warning("DeepSeek extraction error: %s", e)
            return self._extract_mock(text)

    # ------------------------------------------------------------------
    # Instructor mode -- constrained structured output
    # ------------------------------------------------------------------

    async def _extract_with_instructor(self, text: str) -> dict[str, Any]:
        try:
            import instructor
            if self._api_base and "ollama" in self._api_base:
                from openai import OpenAI
                client = instructor.from_openai(
                    OpenAI(base_url=self._api_base, api_key=self._api_key or "ollama"),
                    mode=instructor.Mode.JSON,
                )
            else:
                from openai import OpenAI
                client = instructor.from_openai(
                    OpenAI(api_key=self._api_key),
                )
            resp = client.chat.completions.create(
                model=self._model,
                response_model=self._pydantic_model,
                messages=[
                    {
                        "role": "system",
                        "content": "Extract structured information from the text below. "
                                   "Set fields to null if information is not found.",
                    },
                    {"role": "user", "content": text},
                ],
            )
            return resp.model_dump(exclude_none=False)
        except ImportError:
            logger.warning("instructor not installed, falling back to JSON mode")
            return await self._extract_json_mode(text)

    # ------------------------------------------------------------------
    # JSON mode -- OpenAI compatible API with response_format=json
    # ------------------------------------------------------------------

    async def _extract_json_mode(self, text: str) -> dict[str, Any]:
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=self._api_key,
                base_url=self._api_base,
            )
            schema = self._pydantic_model.model_json_schema()
            resp = client.chat.completions.create(
                model=self._model,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": f"Extract structured information as JSON matching this schema: {json.dumps(schema)}",
                    },
                    {"role": "user", "content": text},
                ],
            )
            content = resp.choices[0].message.content
            if content:
                return json.loads(content)
            return {}
        except ImportError:
            logger.warning("openai not installed, returning empty extraction")
            return {}
