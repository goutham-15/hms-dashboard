from __future__ import annotations

from pathlib import Path
from typing import Iterator

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

from app.utils.logger import get_logger


logger = get_logger(name="document_loader")


class DocumentLoader:
    """
    Single-file document text extractor using docling with OCR-heavy image pipeline.
    """

    _converter = None

    def __init__(self, file_path: str | Path) -> None:
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {self.file_path}")

    @classmethod
    def _get_converter(cls) -> DocumentConverter:
        """Lazy load the DocumentConverter once across instances with OCR pipeline."""
        if cls._converter is None:
            logger.info("Initializing docling DocumentConverter with Image/OCR pipeline...")
            
            # Configure to force OCR on all pages (treating PDF as images)
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = True
            pipeline_options.ocr_options.force_full_page_ocr = True
            pipeline_options.ocr_options.lang = ["eng"]
            
            cls._converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
                }
            )
            logger.info("Converter initialized with forced OCR pipeline.")
        return cls._converter

    def iter_pages_text(self, *, language: str = "en", **kwargs) -> Iterator[tuple[int, str]]:
        """
        Yield text per page using docling.
        """
        converter = self._get_converter()

        try:
            result = converter.convert(self.file_path)
            for page in result.pages:
                page_no = page.page_no
                try:
                    page_doc = result.document.filter(page_nrs={page_no})
                    text = page_doc.export_to_markdown()
                    yield page_no, text
                except Exception as e:
                    logger.warning("Failed to filter page %s: %s", page_no, e)
                    continue
        except Exception as e:
            logger.error("Error during docling conversion on %s: %s", self.file_path.name, str(e))
            raise

    def extract_text(self, *, language: str = "en") -> str:
        """
        Convert the entire file and return combined text.
        """
        parts: list[str] = []
        for page_number, text in self.iter_pages_text(language=language):
            logger.info("Processed page %s: chars=%s file=%s", page_number, len(text), self.file_path.name)
            if text:
                parts.append(text)
        return "\n\n".join(parts).strip()
