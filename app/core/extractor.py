from pathlib import Path
from typing import Optional
from langchain.prompts import PromptTemplate
from langchain.output_parsers import PydanticOutputParser
from langchain_aws import ChatBedrock
from app.models.medical_report import MedicalReportData
from app.core.document_loader import DocumentLoader
from app.utils.config import settings
from app.utils.logger import get_logger


logger = get_logger(name="extractor")


class MedicalReportExtractor:
    """
    LangChain-based extractor for medical reports using Pydantic output parser
    and AWS Bedrock for LLM inference.
    """
    
    def __init__(
        self,
        model_id: Optional[str] = None,
        region: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096
    ):
        """
        Initialize the Medical Report Extractor.
        
        Args:
            model_id: AWS Bedrock model ID (defaults to config)
            region: AWS region (defaults to config)
            temperature: LLM temperature for extraction (0.0 for deterministic)
            max_tokens: Maximum tokens for LLM response
        """
        self.model_id = model_id or settings.aws.bedrock.modelid
        self.region = region or settings.aws.bedrock.region
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        logger.info(f"Initializing MedicalReportExtractor with model: {self.model_id}")
        
        self.llm = ChatBedrock(
            model_id=self.model_id,
            region_name=self.region,
            credentials_profile_name=None,
            model_kwargs={
                "temperature": self.temperature,
                "max_tokens": self.max_tokens
            }
        )
        
        self.parser = PydanticOutputParser(pydantic_object=MedicalReportData)
        
        self.document_loader = DocumentLoader()
        
        self.prompt_template = PromptTemplate(
            template="""You are a medical data extraction specialist. Your task is to extract structured information from medical reports.

Extract the following information from the medical report text below and format it according to the schema provided.

{format_instructions}

Medical Report Text:
{document_text}

Important Instructions:
1. Extract ALL information present in the document accurately
2. For Thyrocare reports: Focus on lab test results with numeric values, units, and reference ranges
3. For SecondMedic reports: Focus on diagnostic imaging findings and impressions
4. If a field is not present in the document, use the default value (empty string "" or empty dict {{}})
5. For the inference field: Synthesize a comprehensive medical summary based on all extracted data
6. Ensure all required fields are filled
7. Convert dates to YYYY-MM-DD format and datetimes to ISO format
8. Be precise with numeric values and units

Output the extracted data in valid JSON format matching the schema.
""",
            input_variables=["document_text"],
            partial_variables={"format_instructions": self.parser.get_format_instructions()}
        )
        
        self.chain = self.prompt_template | self.llm | self.parser
        
        logger.info("MedicalReportExtractor initialized successfully")
    
    def extract_from_text(self, document_text: str) -> MedicalReportData:
        """
        Extract structured data from medical report text.
        
        Args:
            document_text: Raw text extracted from medical report
            
        Returns:
            MedicalReportData object with extracted information
        """
        logger.info(f"Starting extraction from text ({len(document_text)} characters)")
        
        try:
            result = self.chain.invoke({"document_text": document_text})
            logger.info("Extraction completed successfully")
            return result
            
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            logger.exception("Full traceback:")
            raise
    
    def extract_from_pdf(
        self,
        pdf_path: str | Path,
        use_ocr: bool = False,
        ocr_threshold: int = 100
    ) -> MedicalReportData:
        """
        Extract structured data from a PDF medical report.
        
        Args:
            pdf_path: Path to the PDF file
            use_ocr: Force OCR extraction (default: False, uses hybrid)
            ocr_threshold: Minimum characters for direct extraction
            
        Returns:
            MedicalReportData object with extracted information
        """
        pdf_path = Path(pdf_path)
        logger.info(f"Starting extraction from PDF: {pdf_path.name}")
        
        if use_ocr:
            logger.info("Using OCR extraction")
            document_text = self.document_loader.extract_text_with_ocr(pdf_path)
        else:
            logger.info("Using hybrid extraction")
            document_text = self.document_loader.extract_text_hybrid(
                pdf_path, 
                ocr_threshold=ocr_threshold
            )
        
        logger.info(f"Extracted {len(document_text)} characters from PDF")
        
        return self.extract_from_text(document_text)
    
    def validate_extraction(self, data: MedicalReportData) -> bool:
        """
        Validate the extracted data against the Pydantic model.
        
        Args:
            data: MedicalReportData object to validate
            
        Returns:
            True if valid, raises ValidationError if invalid
        """
        try:
            data.model_validate(data.model_dump())
            logger.info("Validation successful")
            return True
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            raise
