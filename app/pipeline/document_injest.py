from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional, Protocol, runtime_checkable

from app.models.medical_report import MedicalReportData
from app.utils.logger import get_logger


logger = get_logger(name="document_injest_pipeline")


@dataclass
class PageText:
    page_number: int
    text: str
    method: str = "unknown"


@dataclass
class ExtractionTask:
    name: str
    query: str
    schema_hint: dict[str, Any]
    target_path: str
    k: int = 6


@dataclass
class IndexResult:
    pages: int
    total_chars: int
    total_chunks: int
    persist_directory: Optional[str] = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    data: dict[str, Any]
    evidence: dict[str, list[dict[str, Any]]]
    warnings: dict[str, list[str]]
    stats: dict[str, Any]


@runtime_checkable
class DocumentLoaderPort(Protocol):
    def iter_pages(self, pdf_path: str | Path) -> Iterator[dict[str, Any] | PageText]:
        ...


@runtime_checkable
class ChunkerPort(Protocol):
    def split(self, text: str) -> list[str]:
        ...


@runtime_checkable
class VectorDBPort(Protocol):
    def add_texts(self, texts: list[str], metadatas: list[dict[str, Any]]) -> int:
        ...

    def search(
        self,
        query: str,
        k: int,
        where: dict[str, Any] | None = None,
    ) -> list[Any]:
        ...


@runtime_checkable
class LLMExtractorPort(Protocol):
    def extract(
        self,
        task: str,
        schema_hint: dict[str, Any],
        context_chunks: list[str] | None = None,
        retrieved_documents: list[Any] | None = None,
    ) -> dict[str, Any]:
        ...


class DocumentInjestPipeline:
    """
    Dependency-injected PDF extraction pipeline.

    The pipeline orchestrates loading, chunking, optional vector indexing/search,
    and LLM extraction. It does not implement OCR, splitting, or model clients.
    """

    def __init__(
        self,
        document_loader: DocumentLoaderPort,
        chunker: ChunkerPort,
        llm_extractor: LLMExtractorPort,
        vector_db: VectorDBPort | None = None,
    ) -> None:
        self.document_loader = document_loader
        self.chunker = chunker
        self.llm_extractor = llm_extractor
        self.vector_db = vector_db

    def index(self, pdf_path: str | Path, source_id: str) -> IndexResult:
        pages_payload, warnings = self._load_pages(pdf_path)
        pages = len(pages_payload)
        total_chars = sum(len(p["text"]) for p in pages_payload)

        chunk_rows = self._chunk_pages(pages_payload)
        total_chunks = len(chunk_rows)

        persist_directory: Optional[str] = None
        if self.vector_db and chunk_rows:
            texts = [row["text"] for row in chunk_rows]
            metadatas = [
                {
                    "source_id": source_id,
                    "page": row["page"],
                    "chunk_index": row["chunk_index"],
                }
                for row in chunk_rows
            ]
            added = self.vector_db.add_texts(texts=texts, metadatas=metadatas)
            if added != total_chunks:
                warnings.append(
                    f"Vector DB reported {added} inserted chunks, expected {total_chunks}."
                )
            persist_directory = str(getattr(self.vector_db, "persist_directory", None) or "") or None

        logger.info(
            "Index complete source_id=%s pages=%s chars=%s chunks=%s warnings=%s",
            source_id,
            pages,
            total_chars,
            total_chunks,
            len(warnings),
        )

        return IndexResult(
            pages=pages,
            total_chars=total_chars,
            total_chunks=total_chunks,
            persist_directory=persist_directory,
            warnings=warnings,
        )

    def extract(
        self,
        pdf_path: str | Path,
        source_id: str,
        tasks: list[ExtractionTask],
        *,
        validate_output: bool = True,
        fallback_max_chars: int = 6000,
    ) -> PipelineResult:
        pages_payload, load_warnings = self._load_pages(pdf_path)
        chunk_rows = self._chunk_pages(pages_payload)

        index_result: Optional[IndexResult] = None
        if self.vector_db and not self._is_indexed(source_id):
            index_result = self.index(pdf_path=pdf_path, source_id=source_id)

        final_data: dict[str, Any] = {
            "staff_details": {},
            "thyrocare": {},
            "second_medic": {},
            "inference": "",
        }
        all_evidence: dict[str, list[dict[str, Any]]] = {}
        all_warnings: dict[str, list[str]] = {}

        for task in tasks:
            task_warnings: list[str] = []
            retrieved_docs: list[Any] = []
            context_chunks: list[str] = []

            if self.vector_db:
                retrieved_docs = self.vector_db.search(
                    query=task.query,
                    k=task.k,
                    where={"source_id": source_id},
                )
                logger.info(
                    "Task=%s retrieved=%s chunks via vector search",
                    task.name,
                    len(retrieved_docs),
                )
            else:
                context_chunks = self._build_fallback_context(
                    task=task,
                    chunk_rows=chunk_rows,
                    max_chars=fallback_max_chars,
                )
                logger.info(
                    "Task=%s using fallback context chunks=%s",
                    task.name,
                    len(context_chunks),
                )

            raw_result = self.llm_extractor.extract(
                task=task.query,
                schema_hint=task.schema_hint,
                context_chunks=context_chunks or None,
                retrieved_documents=retrieved_docs or None,
            )

            task_data = raw_result.get("data") or {}
            task_evidence = self._normalize_evidence(raw_result.get("evidence") or [])
            task_warnings.extend([str(w) for w in (raw_result.get("warnings") or [])])

            task_data, evidence_warnings = self._enforce_evidence(task_data, task_evidence, task.name)
            task_warnings.extend(evidence_warnings)

            if not self._has_non_empty_values(task_data):
                task_warnings.append(
                    f"No reliable values extracted for task '{task.name}'; kept empty output."
                )
                task_data = self._empty_from_schema(task.schema_hint)

            self._merge_task_output(final_data, task.target_path, task_data)
            all_evidence[task.name] = task_evidence
            all_warnings[task.name] = task_warnings

        validation_warning: Optional[str] = None
        if validate_output:
            try:
                validated = MedicalReportData.model_validate(final_data)
                final_data = validated.model_dump()
            except Exception as exc:
                validation_warning = f"Final output validation failed: {exc}"
                logger.warning(validation_warning)

        if validation_warning:
            all_warnings.setdefault("validation", []).append(validation_warning)

        warnings_count = sum(len(v) for v in all_warnings.values())
        stats = {
            "pages": len(pages_payload),
            "total_chars": sum(len(p["text"]) for p in pages_payload),
            "total_chunks": len(chunk_rows),
            "tasks": len(tasks),
            "warnings": warnings_count,
            "indexed": bool(index_result or self.vector_db),
            "persist_directory": getattr(self.vector_db, "persist_directory", None) if self.vector_db else None,
        }

        if load_warnings:
            all_warnings.setdefault("loader", []).extend(load_warnings)
            stats["warnings"] = stats["warnings"] + len(load_warnings)

        logger.info(
            "Extraction complete source_id=%s tasks=%s warnings=%s",
            source_id,
            len(tasks),
            stats["warnings"],
        )

        return PipelineResult(
            data=final_data,
            evidence=all_evidence,
            warnings=all_warnings,
            stats=stats,
        )

    def _load_pages(self, pdf_path: str | Path) -> tuple[list[dict[str, Any]], list[str]]:
        warnings: list[str] = []
        pages_payload: list[dict[str, Any]] = []

        for item in self.document_loader.iter_pages(pdf_path):
            if isinstance(item, dict):
                page_number = int(item.get("page_number") or 0)
                text = str(item.get("text") or "")
                method = str(item.get("method") or "unknown")
            else:
                page_number = int(getattr(item, "page_number", 0))
                text = str(getattr(item, "text", "") or "")
                method = str(getattr(item, "method", "unknown") or "unknown")

            if page_number <= 0:
                warnings.append("Encountered page payload with invalid page_number; skipped.")
                continue

            cleaned = text.strip()
            pages_payload.append(
                {
                    "page": page_number,
                    "text": cleaned,
                    "method": method,
                }
            )

            if not cleaned:
                warnings.append(f"Page {page_number} has empty text after loader stage.")

        logger.info(
            "Loaded pages=%s chars=%s",
            len(pages_payload),
            sum(len(p["text"]) for p in pages_payload),
        )
        return pages_payload, warnings

    def _chunk_pages(self, pages_payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for page in pages_payload:
            page_number = page["page"]
            text = page["text"]
            if not text:
                continue
            chunks = self.chunker.split(text)
            for idx, chunk in enumerate(chunks):
                cleaned = (chunk or "").strip()
                if not cleaned:
                    continue
                rows.append(
                    {
                        "page": page_number,
                        "chunk_index": idx,
                        "text": cleaned,
                    }
                )
        logger.info("Chunking complete chunks=%s", len(rows))
        return rows

    def _is_indexed(self, source_id: str) -> bool:
        if not self.vector_db:
            return False
        try:
            existing = self.vector_db.search(
                query="medical report",
                k=1,
                where={"source_id": source_id},
            )
            return len(existing or []) > 0
        except Exception:
            return False

    def _build_fallback_context(
        self,
        *,
        task: ExtractionTask,
        chunk_rows: list[dict[str, Any]],
        max_chars: int,
    ) -> list[str]:
        tokens = {t.strip().lower() for t in task.query.split() if t.strip()}
        scored_rows: list[tuple[int, dict[str, Any]]] = []

        for row in chunk_rows:
            text_lower = row["text"].lower()
            score = sum(1 for token in tokens if token in text_lower)
            scored_rows.append((score, row))

        scored_rows.sort(key=lambda x: x[0], reverse=True)

        chosen: list[str] = []
        total = 0
        for _, row in scored_rows:
            chunk_text = row["text"]
            if total + len(chunk_text) > max_chars:
                break
            chosen.append(chunk_text)
            total += len(chunk_text)

        return chosen

    def _normalize_evidence(self, evidence_items: list[Any]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in evidence_items:
            if isinstance(item, dict):
                page = item.get("page")
                quote = item.get("quote", "")
                note = item.get("note", "")
            else:
                page = getattr(item, "page", None)
                quote = getattr(item, "quote", "")
                note = getattr(item, "note", "")

            if page is None or not str(quote).strip():
                continue
            normalized.append(
                {
                    "page": int(page),
                    "quote": str(quote).strip(),
                    "note": str(note or "").strip(),
                }
            )
        return normalized

    def _enforce_evidence(
        self,
        data: dict[str, Any],
        evidence: list[dict[str, Any]],
        task_name: str,
    ) -> tuple[dict[str, Any], list[str]]:
        warnings: list[str] = []

        if self._has_non_empty_values(data) and not evidence:
            warnings.append(
                f"Task '{task_name}' produced values without evidence; values were cleared."
            )
            return self._empty_from_schema(data), warnings

        return data, warnings

    def _has_non_empty_values(self, value: Any) -> bool:
        if isinstance(value, dict):
            return any(self._has_non_empty_values(v) for v in value.values())
        if isinstance(value, list):
            return any(self._has_non_empty_values(v) for v in value)
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        return True

    def _empty_from_schema(self, schema: Any) -> Any:
        if isinstance(schema, dict):
            return {k: self._empty_from_schema(v) for k, v in schema.items()}
        if isinstance(schema, list):
            return []
        if isinstance(schema, str):
            return ""
        return None

    def _merge_task_output(self, final_data: dict[str, Any], target_path: str, task_data: Any) -> None:
        if target_path == "":
            if isinstance(task_data, dict):
                final_data.update(task_data)
            return

        keys = target_path.split(".")
        cursor: Any = final_data
        for key in keys[:-1]:
            if key not in cursor or not isinstance(cursor[key], dict):
                cursor[key] = {}
            cursor = cursor[key]

        if len(keys) == 1 and keys[0] == "inference":
            if isinstance(task_data, dict) and "inference" in task_data:
                cursor[keys[-1]] = task_data.get("inference", "")
            else:
                cursor[keys[-1]] = task_data if isinstance(task_data, str) else ""
            return

        cursor[keys[-1]] = task_data


def default_medical_report_tasks() -> list[ExtractionTask]:
    return [
        ExtractionTask(
            name="staff_details",
            query="Extract staff id, name, designation, department, contact, email from this medical report.",
            schema_hint={
                "staff_id": "",
                "name": "",
                "designation": "",
                "department": "",
                "contact": "",
                "email": "",
            },
            target_path="staff_details",
        ),
        ExtractionTask(
            name="thyrocare_core",
            query="Extract Thyrocare report info and patient details only.",
            schema_hint={
                "report_info": {
                    "report_id": "",
                    "report_date": "",
                    "lab_name": "",
                    "status": "",
                },
                "patient_details": {
                    "patient_id": "",
                    "name": "",
                    "age": "",
                    "gender": "",
                    "referred_by": "",
                },
            },
            target_path="thyrocare",
        ),
        ExtractionTask(
            name="second_medic_core",
            query="Extract SecondMedic report info and patient details only.",
            schema_hint={
                "report_info": {
                    "report_date": "",
                    "institution": "",
                    "case_ids": {},
                },
                "patient_details": {
                    "name": "",
                    "age": "",
                    "gender": "",
                },
            },
            target_path="second_medic",
        ),
        ExtractionTask(
            name="inference",
            query="Generate a short clinical inference from extracted report context.",
            schema_hint={"inference": ""},
            target_path="inference",
        ),
    ]


if __name__ == "__main__":
    from uuid import uuid4

    from app.core.document_loader import DocumentLoader

    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except Exception:
        from langchain.text_splitter import RecursiveCharacterTextSplitter  # type: ignore

    @dataclass
    class _Doc:
        page_content: str
        metadata: dict[str, Any]

    class DocumentLoaderAdapter:
        def __init__(self, loader: DocumentLoader):
            self.loader = loader

        def iter_pages(self, pdf_path: str | Path) -> Iterator[dict[str, Any]]:
            for page_number, text, method in self.loader.iter_pdf_pages_text(
                pdf_path,
                use_ocr=True,
            ):
                yield {
                    "page_number": page_number,
                    "text": text,
                    "method": method,
                }

    class LangChainChunker:
        def __init__(self, chunk_size: int = 1500, chunk_overlap: int = 150):
            self.splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                separators=["\n\n", "\n", " ", ""],
            )

        def split(self, text: str) -> list[str]:
            return [c for c in self.splitter.split_text(text) if c.strip()]

    class DummyExtractor:
        def extract(
            self,
            task: str,
            schema_hint: dict[str, Any],
            context_chunks: list[str] | None = None,
            retrieved_documents: list[Any] | None = None,
        ) -> dict[str, Any]:
            del task, context_chunks, retrieved_documents
            return {
                "data": _empty_from_schema_local(schema_hint),
                "evidence": [],
                "warnings": ["Dummy extractor used; no LLM extraction performed."],
            }

    class InMemoryVectorDB:
        def __init__(self) -> None:
            self.persist_directory = "memory://vector"
            self._rows: list[tuple[str, dict[str, Any]]] = []

        def add_texts(self, texts: list[str], metadatas: list[dict[str, Any]]) -> int:
            for text, meta in zip(texts, metadatas):
                self._rows.append((text, meta))
            return len(texts)

        def search(
            self,
            query: str,
            k: int,
            where: dict[str, Any] | None = None,
        ) -> list[_Doc]:
            query_tokens = {token.lower() for token in query.split() if token.strip()}

            filtered: list[tuple[str, dict[str, Any]]] = []
            for text, meta in self._rows:
                if where and any(meta.get(mk) != mv for mk, mv in where.items()):
                    continue
                filtered.append((text, meta))

            scored: list[tuple[int, _Doc]] = []
            for text, meta in filtered:
                content = text.lower()
                score = sum(1 for token in query_tokens if token in content)
                scored.append((score, _Doc(page_content=text, metadata=meta)))

            scored.sort(key=lambda item: item[0], reverse=True)
            return [doc for _, doc in scored[:k]]

    def _empty_from_schema_local(schema: Any) -> Any:
        if isinstance(schema, dict):
            return {k: _empty_from_schema_local(v) for k, v in schema.items()}
        if isinstance(schema, list):
            return []
        if isinstance(schema, str):
            return ""
        return None

    root = Path(__file__).resolve().parents[2]
    sample_pdf = root / "samples" / "thyrocare.pdf"

    if not sample_pdf.exists():
        print(f"Sample PDF not found: {sample_pdf}")
    else:
        source_id = f"sample-{uuid4().hex[:8]}"
        tasks = default_medical_report_tasks()

        loader = DocumentLoaderAdapter(DocumentLoader())
        chunker = LangChainChunker()
        extractor = DummyExtractor()

        pipeline_with_vector = DocumentInjestPipeline(
            document_loader=loader,
            chunker=chunker,
            llm_extractor=extractor,
            vector_db=InMemoryVectorDB(),
        )
        index_result = pipeline_with_vector.index(sample_pdf, source_id)
        result_with_vector = pipeline_with_vector.extract(
            sample_pdf,
            source_id,
            tasks,
            validate_output=False,
        )
        print(
            "with_vector_db "
            f"pages={index_result.pages} chunks={index_result.total_chunks} "
            f"warnings={result_with_vector.stats['warnings']}"
        )

        pipeline_without_vector = DocumentInjestPipeline(
            document_loader=loader,
            chunker=chunker,
            llm_extractor=extractor,
            vector_db=None,
        )
        result_without_vector = pipeline_without_vector.extract(
            sample_pdf,
            source_id,
            tasks,
            validate_output=False,
        )
        print(
            "without_vector_db "
            f"pages={result_without_vector.stats['pages']} "
            f"chunks={result_without_vector.stats['total_chunks']} "
            f"warnings={result_without_vector.stats['warnings']}"
        )
