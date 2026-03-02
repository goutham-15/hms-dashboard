from pathlib import Path
from typing import Any, Iterable, Optional

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except Exception:  # pragma: no cover
    from langchain.text_splitter import RecursiveCharacterTextSplitter  # type: ignore


try:
    from langchain_chroma import Chroma
except Exception:  # pragma: no cover
    from langchain_community.vectorstores import Chroma  # type: ignore


class ChromaVectorDB:
    """
    Minimal Chroma wrapper for storing OCR chunks with page metadata.
    """

    def __init__(
        self,
        *,
        persist_directory: str | Path,
        collection_name: str,
        embedding_function: Any,
    ):
        self.persist_directory = str(persist_directory)
        self.collection_name = collection_name
        self.embedding_function = embedding_function

        self.store = Chroma(
            collection_name=self.collection_name,
            embedding_function=self.embedding_function,
            persist_directory=self.persist_directory,
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

        if texts:
            self.store.add_texts(texts=texts, metadatas=metadatas)
        return len(texts)

    def search(
        self,
        query: str,
        *,
        k: int = 6,
        where: Optional[dict[str, Any]] = None,
    ):
        """
        Returns LangChain Document objects.
        """
        if where:
            return self.store.similarity_search(query=query, k=k, filter=where)
        return self.store.similarity_search(query=query, k=k)
