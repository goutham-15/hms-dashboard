from pathlib import Path
from typing import Any, Iterable, Optional

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except Exception:  # pragma: no cover
    from langchain.text_splitter import RecursiveCharacterTextSplitter  # type: ignore


import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.utils import embedding_functions
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
        embedding_model: str = "all-MiniLM-L6-v2",
    ):
        self.persist_directory = str(persist_directory) if persist_directory else ""
        self.collection_name = collection_name
        self.embedding_function = embedding_function
        self.embedding_model = embedding_model

        if self.persist_directory:
            self.client = chromadb.PersistentClient(
                path=self.persist_directory,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        else:
            self.client = chromadb.Client(
                settings=ChromaSettings(anonymized_telemetry=False, is_persistent=False),
            )

        ef = self.embedding_function or embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=self.embedding_model
        )
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
