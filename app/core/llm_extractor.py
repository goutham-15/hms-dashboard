import json
from typing import Any, Optional

from pydantic import BaseModel, Field
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate

def _join_context(chunks: list[str], *, max_chars: int) -> str:
    buf: list[str] = []
    total = 0
    for c in chunks:
        if not c:
            continue
        if total + len(c) + 2 > max_chars:
            break
        buf.append(c)
        total += len(c) + 2
    return "\n\n".join(buf)


class EvidenceSnippet(BaseModel):
    page: Optional[int] = Field(None, description="1-based page number if available in metadata.")
    quote: str = Field(..., description="Short verbatim snippet (<= 25 words) from the retrieved context.")
    note: Optional[str] = Field("", description="What this snippet supports.")


class JSONExtractionResult(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict, description="Extracted JSON object.")
    evidence: list[EvidenceSnippet] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RAGLLMExtractor:
    """
    Targeted JSON extraction using only retrieved RAG context (small prompts).
    """

    def __init__(self, *, llm: Any):
        self.llm = llm
        self.parser = PydanticOutputParser(pydantic_object=JSONExtractionResult)

        self.prompt = PromptTemplate(
            template="""You are a strict JSON information extraction engine.

You will be given:
- task: what to extract
- schema_hint: a JSON-like shape (keys) to follow
- context: retrieved OCR chunks (may be incomplete)

Rules:
1) Use ONLY the provided context. If a value is not explicitly present, omit it or leave it empty.
2) Return valid JSON that matches the output schema exactly.
3) For every populated key in data, add at least one evidence snippet (<= 25 words quote).
4) If context seems insufficient, add a warning string explaining what is missing.

task:
{task}

schema_hint:
{schema_hint}

context:
{context}

{format_instructions}
""",
            input_variables=["task", "schema_hint", "context"],
            partial_variables={"format_instructions": self.parser.get_format_instructions()},
        )

        self.chain = self.prompt | self.llm | self.parser

    def extract(
        self,
        *,
        task: str,
        retrieved_documents: list[Any],
        schema_hint: dict[str, Any] | None = None,
        max_context_chars: int = 12_000,
    ) -> JSONExtractionResult:
        chunks: list[str] = []
        for d in retrieved_documents or []:
            try:
                chunks.append(getattr(d, "page_content", "") or "")
            except Exception:
                continue

        context = _join_context(chunks, max_chars=max_context_chars)
        return self.chain.invoke(
            {
                "task": task,
                "schema_hint": json.dumps(schema_hint or {}, ensure_ascii=False),
                "context": context,
            }
        )
