from pathlib import Path
import os
import threading
from typing import Any, Iterable, Optional

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except Exception:  # pragma: no cover
    from langchain.text_splitter import RecursiveCharacterTextSplitter  # type: ignore

from langchain_core.documents import Document


class ChromaVectorDB:
    """
    Minimal ChromaDB wrapper for storing OCR chunks with page metadata.
    """

    def __init__(
        self,
        *,
        persist_directory: str | Path | None = None,
        collection_name: str,
        embedding_function: Any | None = None,
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
        self.embedding_function = embedding_function

        if self.persist_directory:
            self.client = chromadb.PersistentClient(
                path=self.persist_directory,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        else:
            self.client = chromadb.Client(
                settings=ChromaSettings(anonymized_telemetry=False, is_persistent=False),
            )

        ef = self.embedding_function or get_default_embedding_function()
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=ef,
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

    def delete_source(self, *, source_id: str) -> int:
        """
        Delete all vectors for a specific document (source_id).
        """
        got = self.collection.get(where={"source_id": source_id}, include=[])
        ids = got.get("ids") or []
        if not ids:
            return 0
        self.collection.delete(ids=ids)
        return len(ids)


def _hash_embedding_function(texts: list[str]) -> list[list[float]]:
    """
    Deterministic local embedding to avoid model downloads.

    Not semantically strong, but sufficient for lightweight retrieval without network access.
    """
    import hashlib

    dims = 256
    out: list[list[float]] = []
    for t in texts:
        vec = [0.0] * dims
        digest = hashlib.sha256((t or "").encode("utf-8", errors="ignore")).digest()
        for i, byte in enumerate(digest):
            vec[i % dims] += (byte / 255.0) * 2.0 - 1.0
        out.append(vec)
    return out


_ST_MODELS: dict[str, Any] = {}
_ST_LOCK = threading.Lock()


def _get_sentence_transformer(model_name: str):
    """
    Load and cache a SentenceTransformer model once per process.
    """
    name = (model_name or "").strip() or "all-MiniLM-L6-v2"
    with _ST_LOCK:
        cached = _ST_MODELS.get(name)
        if cached is not None:
            return cached

        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise ModuleNotFoundError(
                "sentence-transformers is required for SentenceTransformer embeddings. "
                "Install `sentence-transformers` or use the default hash embedding."
            ) from exc

        try:
            model = SentenceTransformer(name)
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                f"Failed to load SentenceTransformer model '{name}'. "
                "If running offline, pre-download/cached models are required."
            ) from exc

        _ST_MODELS[name] = model
        return model


def sentence_transformer_embedding_function(texts: list[str], *, model_name: str) -> list[list[float]]:
    """
    Chroma-compatible embedding function using a cached SentenceTransformer model.
    """
    model = _get_sentence_transformer(model_name)
    cleaned = [(t or "") for t in texts]
    vectors = model.encode(cleaned, normalize_embeddings=True)
    return [list(map(float, row)) for row in vectors.tolist()]


def get_default_embedding_function():
    """
    Returns a process-wide embedding function.

    Defaults to deterministic hash embeddings. Set:
    - `HMS_VECTOR_EMBEDDING_BACKEND=sentence_transformer`
    - `HMS_VECTOR_EMBEDDING_MODEL=<model-name>` (optional)
    """
    backend = (os.environ.get("HMS_VECTOR_EMBEDDING_BACKEND") or "hash").strip().lower()
    if backend in {"sentence_transformer", "sentence-transformer", "st"}:
        model_name = os.environ.get("HMS_VECTOR_EMBEDDING_MODEL") or "all-MiniLM-L6-v2"

        def _ef(texts: list[str]) -> list[list[float]]:
            return sentence_transformer_embedding_function(texts, model_name=model_name)

        return _ef

    return _hash_embedding_function
