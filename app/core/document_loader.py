from pathlib import Path
from typing import Optional, List
import PyPDF2
from pdf2image import convert_from_path, pdfinfo_from_path
import pytesseract
from app.utils.logger import get_logger


logger = get_logger(name="document_loader")


class DocumentLoader:
    """
    A class to load PDF documents and extract text using both direct extraction and OCR.
    """
    
    def __init__(self, tesseract_cmd: Optional[str] = None):
        """
        Initialize the DocumentLoader.
        
        Args:
            tesseract_cmd: Path to tesseract executable (optional, uses system default if not provided)
        """
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    
    def extract_text_from_pdf(self, pdf_path: str | Path) -> str:
        """
        Extract text from PDF using PyPDF2 direct extraction.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Extracted text as a string
        """
        pdf_path = Path(pdf_path)
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        text = ""
        try:
            with open(pdf_path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                num_pages = len(pdf_reader.pages)
                
                logger.info(f"Extracting text from {num_pages} pages in {pdf_path.name}")
                
                for page_num in range(num_pages):
                    page = pdf_reader.pages[page_num]
                    page_text = page.extract_text()
                    text += page_text + "\n"
                    
                logger.info(f"Extracted {len(text)} characters from {pdf_path.name}")
                
        except Exception as e:
            logger.error(f"Error extracting text from {pdf_path.name}: {e}")
            raise
        
        return text.strip()
    
    def extract_text_with_ocr(
        self, 
        pdf_path: str | Path,
        dpi: int = 300,
        language: str = 'eng'
    ) -> str:
        """
        Extract text from PDF using OCR (Optical Character Recognition).
        Useful for scanned documents or PDFs with images.
        
        Args:
            pdf_path: Path to the PDF file
            dpi: Resolution for image conversion (higher = better quality but slower)
            language: Tesseract language code (default: 'eng' for English)
            
        Returns:
            Extracted text as a string
        """
        pdf_path = Path(pdf_path)
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        text = ""
        try:
            logger.info(f"Converting PDF to images at {dpi} DPI: {pdf_path.name}")
            images = convert_from_path(pdf_path, dpi=dpi)
            
            logger.info(f"Performing OCR on {len(images)} pages")
            
            for page_num, image in enumerate(images, 1):
                logger.info(f"Processing page {page_num}/{len(images)}")
                page_text = pytesseract.image_to_string(image, lang=language)
                text += page_text + "\n"
            
            logger.info(f"OCR completed. Extracted {len(text)} characters from {pdf_path.name}")
            
        except Exception as e:
            logger.error(f"Error performing OCR on {pdf_path.name}: {e}")
            raise
        
        return text.strip()

    def extract_page_text_with_ocr(
        self,
        pdf_path: str | Path,
        page_number: int,
        dpi: int = 300,
        language: str = "eng",
    ) -> str:
        """
        OCR a single 1-based page from a PDF.

        This avoids building one huge OCR text blob for the whole document, and
        enables page-by-page downstream processing.
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        if page_number < 1:
            raise ValueError("page_number must be >= 1")

        logger.info(f"Converting page {page_number} to image at {dpi} DPI: {pdf_path.name}")
        images = convert_from_path(pdf_path, dpi=dpi, first_page=page_number, last_page=page_number)
        if not images:
            return ""
        return pytesseract.image_to_string(images[0], lang=language).strip()

    def iter_pdf_pages_text(
        self,
        pdf_path: str | Path,
        use_ocr: bool = False,
        ocr_threshold: int = 100,
        dpi: int = 300,
        language: str = "eng",
    ):
        """
        Yield (page_number, page_text, method) for each page in the PDF.

        - If use_ocr=True, OCR every page.
        - Otherwise, try direct text extraction per page; if the extracted text
          is shorter than ocr_threshold characters, OCR that page only.
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        try:
            info = pdfinfo_from_path(pdf_path)
            num_pages = int(info.get("Pages", 0))
        except Exception:
            num_pages = 0

        with open(pdf_path, "rb") as f:
            pdf_reader = PyPDF2.PdfReader(f)
            if not num_pages:
                num_pages = len(pdf_reader.pages)

            logger.info(f"Iterating {num_pages} pages for incremental extraction: {pdf_path.name}")

            for idx in range(num_pages):
                page_number = idx + 1
                page_text = ""
                method = "direct"

                if not use_ocr:
                    try:
                        page_text = (pdf_reader.pages[idx].extract_text() or "").strip()
                    except Exception as e:
                        logger.warning(f"Direct extraction failed for page {page_number}: {e}")
                        page_text = ""

                if use_ocr or len(page_text) < ocr_threshold:
                    method = "ocr"
                    try:
                        page_text = self.extract_page_text_with_ocr(
                            pdf_path,
                            page_number=page_number,
                            dpi=dpi,
                            language=language,
                        )
                    except Exception as e:
                        logger.error(f"OCR failed for page {page_number}: {e}")
                        page_text = ""

                yield page_number, page_text, method
    
    def extract_text_hybrid(
        self,
        pdf_path: str | Path,
        ocr_threshold: int = 100,
        dpi: int = 300,
        language: str = 'eng'
    ) -> str:
        """
        Hybrid approach: Try direct extraction first, fall back to OCR if insufficient text.
        
        Args:
            pdf_path: Path to the PDF file
            ocr_threshold: Minimum characters needed to skip OCR (default: 100)
            dpi: Resolution for OCR image conversion
            language: Tesseract language code
            
        Returns:
            Extracted text as a string
        """
        pdf_path = Path(pdf_path)
        
        logger.info(f"Starting hybrid extraction for {pdf_path.name}")
        
        text = self.extract_text_from_pdf(pdf_path)
        
        if len(text) < ocr_threshold:
            logger.info(f"Direct extraction yielded only {len(text)} characters. Falling back to OCR.")
            text = self.extract_text_with_ocr(pdf_path, dpi=dpi, language=language)
        else:
            logger.info(f"Direct extraction successful with {len(text)} characters.")
        
        return text
    
    def extract_text_from_multiple_pdfs(
        self,
        pdf_paths: List[str | Path],
        use_ocr: bool = False,
        dpi: int = 300,
        language: str = 'eng'
    ) -> dict[str, str]:
        """
        Extract text from multiple PDF files.
        
        Args:
            pdf_paths: List of paths to PDF files
            use_ocr: Whether to use OCR (default: False, uses direct extraction)
            dpi: Resolution for OCR
            language: Tesseract language code
            
        Returns:
            Dictionary mapping file paths to extracted text
        """
        results = {}
        
        for pdf_path in pdf_paths:
            pdf_path = Path(pdf_path)
            logger.info(f"Processing {pdf_path.name}")
            
            try:
                if use_ocr:
                    text = self.extract_text_with_ocr(pdf_path, dpi=dpi, language=language)
                else:
                    text = self.extract_text_hybrid(pdf_path, dpi=dpi, language=language)
                
                results[str(pdf_path)] = text
                
            except Exception as e:
                logger.error(f"Failed to process {pdf_path.name}: {e}")
                results[str(pdf_path)] = ""
        
        return results
    
    def get_pdf_metadata(self, pdf_path: str | Path) -> dict:
        """
        Extract metadata from PDF file.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Dictionary containing PDF metadata
        """
        pdf_path = Path(pdf_path)
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        metadata = {}
        
        try:
            with open(pdf_path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                
                metadata['num_pages'] = len(pdf_reader.pages)
                metadata['file_size'] = pdf_path.stat().st_size
                
                if pdf_reader.metadata:
                    for key, value in pdf_reader.metadata.items():
                        metadata[key] = value
                        
        except Exception as e:
            logger.error(f"Error extracting metadata from {pdf_path.name}: {e}")
            raise
        
        return metadata
