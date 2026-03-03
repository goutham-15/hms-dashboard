from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.core.document_loader import DocumentLoader
from app.core.chunking import TaggedRecursiveTextChunker
from app.core.vector_db import VectorDB
from app.core.llm.extraction import MedicalReportExtractor
from app.aws.client import AWSClient
from app.utils.config import settings
from app.utils.logger import get_logger

logger = get_logger(name="document_injest")

class DocumentIngestor:
    """
    Main entry point for processing and ingesting medical reports.
    """
    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {self.file_path}")
        
        self.source_id = uuid4().hex[:12]
        logger.info("Initialized DocumentIngestor for file: %s (source_id=%s)", self.file_path, self.source_id)

    def process(self) -> Dict[str, Any]:
        """
        Executes the ingestion pipeline: OCR -> Chunking -> Vector DB insertion.
        """
        logger.info("Starting processing for source_id=%s", self.source_id)
        
        # 1. OCR / Text Extraction
        logger.info("Performing OCR on document: %s", self.file_path.name)
        loader = DocumentLoader(self.file_path)
        pages = list(loader.iter_pages_text(dpi=150))
        full_text = "\n\n".join([text for _, text in pages]).strip()
        logger.info("OCR complete. Extracted %d pages, %d characters.", len(pages), len(full_text))
        
        # 2. Chunking
        logger.info("Chunking extracted text...")
        chunker = TaggedRecursiveTextChunker()
        chunks = list(
            chunker.iter_tagged_chunks(
                pages=pages,
                extra_metadata={"file_name": self.file_path.name},
            )
        )
        logger.info("Chunking complete. Created %d chunks.", len(chunks))
        
        # 3. Vector DB Insertion
        logger.info("Inserting chunks into Vector DB...")
        vector_db = VectorDB(
            persist_directory=settings.vector_db.persist_directory,
            collection_name=settings.vector_db.collection_name,
        )
        inserted = vector_db.add_chunks(source_id=self.source_id, chunks=chunks)
        logger.info("Vector DB insertion complete. Inserted %d chunks.", inserted)

        logger.info("Running LLM extraction...")
        aws_client = AWSClient()
        llm = aws_client.bedrock_chat(model_kwargs={"temperature": 0.0})
        extractor = MedicalReportExtractor(llm=llm, vector_db=vector_db)
        llm_response = extractor.extract(full_text=full_text, source_id=self.source_id).model_dump(mode="json")
        logger.info("LLM extraction complete.")
        
        return {
            "source_id": self.source_id,
            "file_name": self.file_path.name,
            "full_text": full_text,
            "chunks": chunks,
            "llm_response": llm_response,
            "vector_db_collection": settings.vector_db.collection_name
        }
