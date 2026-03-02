from __future__ import annotations

from pathlib import Path
from typing import Iterator, Optional

from pdf2image import convert_from_path, pdfinfo_from_path
from PIL import Image
import pytesseract

from app.utils.logger import get_logger


logger = get_logger(name="document_loader")


class DocumentLoader:
    """
    Single-file OCR text extractor.

    This loader takes one file path (PDF or image) and returns OCR text only.
    """

    def __init__(self, file_path: str | Path, *, tesseract_cmd: Optional[str] = None) -> None:
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {self.file_path}")

        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    @staticmethod
    def _ocr_image(image: Image.Image, *, language: str) -> str:
        return (pytesseract.image_to_string(image, lang=language) or "").strip()

    def iter_pages_text(self, *, dpi: int = 300, language: str = "eng") -> Iterator[tuple[int, str]]:
        """
        Yield OCR text per page for PDFs, or a single (1, text) for images.
        """
        suffix = self.file_path.suffix.lower()

        if suffix == ".pdf":
            try:
                info = pdfinfo_from_path(self.file_path)
                num_pages = int(info.get("Pages", 0))
            except Exception:
                num_pages = 0

            if num_pages <= 0:
                logger.warning("Unable to detect PDF page count; attempting a full conversion: %s", self.file_path.name)
                images = convert_from_path(self.file_path, dpi=dpi)
                for idx, image in enumerate(images, start=1):
                    yield idx, self._ocr_image(image, language=language)
                return

            for page_number in range(1, num_pages + 1):
                images = convert_from_path(
                    self.file_path,
                    dpi=dpi,
                    first_page=page_number,
                    last_page=page_number,
                )
                if not images:
                    yield page_number, ""
                    continue
                yield page_number, self._ocr_image(images[0], language=language)
            return

        # Assume image-like input (png/jpg/etc.)
        with Image.open(self.file_path) as image:
            yield 1, self._ocr_image(image, language=language)

    def extract_text(self, *, dpi: int = 300, language: str = "eng") -> str:
        """
        OCR the entire file and return combined text.
        """
        parts: list[str] = []
        for page_number, text in self.iter_pages_text(dpi=dpi, language=language):
            logger.info("OCR page %s: chars=%s file=%s", page_number, len(text), self.file_path.name)
            if text:
                parts.append(text)
        return "\n\n".join(parts).strip()

