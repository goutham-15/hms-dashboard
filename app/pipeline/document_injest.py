from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4
import hashlib

from app.core.document_loader import DocumentLoader
from app.core.chunking import TaggedRecursiveTextChunker
from app.core.vector_db import VectorDB
from app.core.llm.extraction import MedicalReportExtractor
from app.aws.client import AWSClient
from app.db.database import DatabaseManager
from app.utils.config import settings
from app.utils.logger import get_logger

logger = get_logger(name="document_injest")

class DocumentIngestor:
    """
    Main entry point for processing and ingesting medical reports.
    """
    def __init__(self, file_path: str | Path, skip_if_exists: bool = True):
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {self.file_path}")
        
        self.skip_if_exists = skip_if_exists
        self.file_hash = self._compute_file_hash()
        self.source_id = self.file_hash[:12]  # Use first 12 chars of hash as source_id
        logger.info("Initialized DocumentIngestor for file: %s (source_id=%s)", self.file_path, self.source_id)

    def _compute_file_hash(self) -> str:
        """Compute SHA256 hash of the file content."""
        sha256_hash = hashlib.sha256()
        with open(self.file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _check_if_already_processed(self) -> bool:
        """
        Check if this file has already been processed by looking for the source_id in vector DB.
        Returns True if already processed, False otherwise.
        """
        try:
            vector_db = VectorDB(
                persist_directory=settings.vector_db.persist_directory,
                collection_name=settings.vector_db.collection_name,
            )
            # Check if any chunks exist with this source_id
            result = vector_db.get(
                where={"source_id": self.source_id},
                include=["metadatas"]
            )
            
            if result and result.get("metadatas") and len(result["metadatas"]) > 0:
                logger.info("File already processed (source_id=%s). Skipping.", self.source_id)
                return True
            
            return False
        except Exception as e:
            logger.warning("Error checking if file already processed: %s. Proceeding with processing.", e)
            return False

    def process(self) -> Dict[str, Any]:
        """
        Executes the ingestion pipeline: OCR -> Chunking -> Vector DB insertion.
        Skips processing if file has already been processed (based on file hash).
        """
        logger.info("Starting processing for source_id=%s", self.source_id)
        
        # Check if already processed
        if self.skip_if_exists and self._check_if_already_processed():
            return {
                "source_id": self.source_id,
                "file_name": self.file_path.name,
                "status": "skipped",
                "reason": "File already processed"
            }
        
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
        
        # Perform extraction
        profile = extractor.extract(full_text=full_text, source_id=self.source_id)
        llm_response = profile.model_dump(mode="json")
        logger.info("LLM extraction complete.")

        # 4. Database Insertion
        logger.info("Upserting record to database...")
        db_manager = DatabaseManager()
        db_manager.upsert_faculty_health_record(profile, source_id=self.source_id)
        logger.info("Database upsert complete.")
        
        return {
            "source_id": self.source_id,
            "file_name": self.file_path.name,
            "full_text": full_text,
            "chunks": chunks,
            "llm_response": llm_response,
            "vector_db_collection": settings.vector_db.collection_name,
            "status": "processed"
        }
