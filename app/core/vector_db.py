from pathlib import Path
from typing import Any, Iterable, Optional
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings


EMBEDDING_FUNCTION = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")


class _ChromaEmbeddingFunctionAdapter:
    def __init__(self, embeddings: HuggingFaceEmbeddings):
        self._embeddings = embeddings

    def __call__(self, input: list[str]) -> list[list[float]]:
        cleaned = [(t or "") for t in input]
        vectors = self._embeddings.embed_documents(cleaned)
        return [list(map(float, v)) for v in vectors]

    def name(self) -> str:
        model_name = getattr(self._embeddings, "model_name", None) or "all-MiniLM-L6-v2"
        return f"huggingface:{model_name}"


class ChromaVectorDB:
    """
    Minimal ChromaDB wrapper for storing OCR chunks with page metadata.
    """

    def __init__(
        self,
        *,
        persist_directory: str | Path | None = None,
        collection_name: str
    ):
        try:
            import chromadb  # type: ignore
            from chromadb.config import Settings as ChromaSettings  # type: ignore
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise ModuleNotFoundError(
                "chromadb is required to use ChromaVectorDB. Install `chromadb` to enable vector storage."
            ) from exc

        self.persist_directory = str(persist_directory) if persist_directory else ""
        self.collection_name = collection_name

        if self.persist_directory:
            self.client = chromadb.PersistentClient(
                path=self.persist_directory,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        else:
            self.client = chromadb.Client(
                settings=ChromaSettings(anonymized_telemetry=False, is_persistent=False),
            )


        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=_ChromaEmbeddingFunctionAdapter(EMBEDDING_FUNCTION),
        )

    def add_pages(
        self,
        *,
        source_id: str,
        pages: Iterable[tuple[int, str]],
        chunk_size: int = 1500,
        chunk_overlap: int = 150,
        extra_metadata: Optional[dict[str, Any]] = None,
    ) -> int:
        texts: list[str] = []
        metadatas: list[dict[str, Any]] = []
        ids: list[str] = []

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", " ", ""],
        )

        for page_number, page_text in pages:
            cleaned = (page_text or "").strip()
            if not cleaned:
                continue
            chunks = [c.strip() for c in splitter.split_text(cleaned) if c.strip()]
            for chunk_index, chunk in enumerate(chunks):
                texts.append(chunk)
                metadatas.append(
                    {
                        "source_id": source_id,
                        "page": page_number,
                        "chunk_index": chunk_index,
                        **(extra_metadata or {}),
                    }
                )
                ids.append(f"{source_id}:{page_number}:{chunk_index}")

        if texts:
            self.collection.add(documents=texts, metadatas=metadatas, ids=ids)
        return len(texts)

    def add_chunks(
        self,
        *,
        source_id: str,
        chunks: Iterable[tuple[str, dict[str, Any]]],
    ) -> int:
        texts: list[str] = []
        metadatas: list[dict[str, Any]] = []
        ids: list[str] = []

        for idx, (text, meta) in enumerate(chunks):
            cleaned = (text or "").strip()
            if not cleaned:
                continue
            metadata = {"source_id": source_id, **(meta or {})}
            page = metadata.get("page", 0) or 0
            chunk_index = metadata.get("chunk_index", idx)
            ids.append(f"{source_id}:{page}:{chunk_index}:{idx}")
            texts.append(cleaned)
            metadatas.append(metadata)

        if texts:
            self.collection.add(documents=texts, metadatas=metadatas, ids=ids)
        return len(texts)

    def _normalize_where(self, where: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if not where or len(where) <= 1:
            return where
        # If it already starts with an operator, it might be fine, but if it has multiple keys, ChromaDB needs a single top-level operator
        if all(str(k).startswith("$") for k in where.keys()):
            return where
        return {"$and": [{k: v} for k, v in where.items()]}

    def get(self, where: Optional[dict[str, Any]] = None, include: Optional[list[str]] = None):
        """
        Thin wrapper around collection.get with filter normalization.
        """
        where = self._normalize_where(where)
        return self.collection.get(where=where, include=include or [])

    def search(
        self,
        query: str,
        *,
        k: int = 6,
        where: Optional[dict[str, Any]] = None,
    ):
        """
        Returns LangChain `Document` objects.
        """
        where = self._normalize_where(where)
        res = self.collection.query(
            query_texts=[query],
            n_results=k,
            where=where,
            include=["documents", "metadatas"],
        )
        documents = (res.get("documents") or [[]])[0] or []
        metadatas = (res.get("metadatas") or [[]])[0] or []
        out: list[Document] = []
        for text, meta in zip(documents, metadatas):
            out.append(Document(page_content=text or "", metadata=meta or {}))
        return out

    def similarity_search(
        self,
        query: str,
        *,
        k: int = 6,
        filter: Optional[dict[str, Any]] = None,
    ):
        """
        Alias for search to match LangChain-like interface.
        """
        return self.search(query, k=k, where=filter)

    def delete_source(self, source_id: str) -> int:
        """
        Delete all documents and metadata associated with a source_id.
        """
        where = self._normalize_where({"source_id": source_id})
        res = self.collection.get(where=where, include=[])
        ids = res.get("ids") or []
        if ids:
            self.collection.delete(ids=ids)
        return len(ids)

    def add_documents(self, chunks: Iterable[tuple[str, dict[str, Any]]], source_id: str = "") -> int:
        """
        Alias for add_chunks to match expected API in main.py.
        """
        return self.add_chunks(source_id=source_id, chunks=chunks)


VectorDB = ChromaVectorDB
