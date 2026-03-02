from pathlib import Path
from typing import Any, Optional
import json
from copy import deepcopy
import boto3
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain_aws import ChatBedrock
from app.models.medical_report import MedicalReportData
from app.models.incremental_extraction import (
    DocumentType,
    IncrementalExtractionResult,
    IncrementalPageUpdate,
    InferenceOnly,
)
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
        self.model_id = model_id or settings.aws.bedrock.model_id
        self.region = region or settings.aws.bedrock.region
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        logger.info(f"Initializing MedicalReportExtractor with model: {self.model_id}")
        
        bedrock_client = boto3.client(
            "bedrock-runtime",
            region_name=self.region,
            aws_access_key_id=settings.aws.access_key,
            aws_secret_access_key=settings.aws.secret_key
        )
        
        self.llm = ChatBedrock(
            model_id=self.model_id,
            client=bedrock_client,
            model_kwargs={
                "temperature": self.temperature,
                "max_tokens": self.max_tokens
            }
        )
        
        self.parser = PydanticOutputParser(pydantic_object=MedicalReportData)
        self.page_update_parser = PydanticOutputParser(pydantic_object=IncrementalPageUpdate)
        self.inference_parser = PydanticOutputParser(pydantic_object=InferenceOnly)
        
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

        self.page_update_prompt = PromptTemplate(
            template="""You are an information extraction engine that updates a structured state incrementally from ONE PDF page at a time.

You will be given:
- current_state (JSON): compact structured state from previous pages (may omit large arrays such as full test lists)
- running_summary: a short summary so far
- page_number: 1-based page index
- page_text: OCR/text of the current page

Rules:
1) Extract ONLY what is explicitly present in page_text. Do not guess or infer missing identifiers.
2) Do NOT overwrite non-empty existing values in current_state unless page_text clearly contradicts them.
   - If there is a contradiction, add an item to conflicts[] and do not overwrite automatically.
3) Every non-empty value you add in updates/new_test_results/new_diagnostics MUST have an evidence item with:
   - field_path (dotted)
   - page (page_number)
   - quote: a short verbatim snippet from page_text (<= 25 words)
4) new_test_results and new_diagnostics must contain ONLY items visible on this page.
5) Update running_summary to be at most ~8 lines; include key identifiers found so far; do not add anything not supported by evidence.

current_state (JSON):
{current_state}

running_summary:
{running_summary}

page_number: {page_number}

page_text:
{page_text}

{format_instructions}
""",
            input_variables=["current_state", "running_summary", "page_number", "page_text"],
            partial_variables={
                "format_instructions": self.page_update_parser.get_format_instructions()
            },
        )

        self.inference_prompt = PromptTemplate(
            template="""You are a medical data summarization engine.

Using ONLY the structured state and running summary below, write a 2-5 sentence overall medical inference.
Do not add any facts that are not supported by the structured state or running summary.

structured_state (JSON):
{structured_state}

running_summary:
{running_summary}

{format_instructions}
""",
            input_variables=["structured_state", "running_summary"],
            partial_variables={
                "format_instructions": self.inference_parser.get_format_instructions()
            },
        )
        
        self.chain = self.prompt_template | self.llm | self.parser
        self.page_update_chain = self.page_update_prompt | self.llm | self.page_update_parser
        self.inference_chain = self.inference_prompt | self.llm | self.inference_parser
        
        logger.info("MedicalReportExtractor initialized successfully")

    @staticmethod
    def _is_empty_value(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str) and value.strip() == "":
            return True
        if isinstance(value, (list, tuple, set)) and len(value) == 0:
            return True
        if isinstance(value, dict) and len(value) == 0:
            return True
        return False

    @classmethod
    def _deep_merge_keep_existing(cls, base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
        """
        Deep merge updates into base, but do not overwrite non-empty scalars.
        Lists are replaced only if base list is empty.
        """
        for key, incoming in (updates or {}).items():
            if key not in base:
                if not cls._is_empty_value(incoming):
                    base[key] = incoming
                continue

            existing = base.get(key)

            if isinstance(existing, dict) and isinstance(incoming, dict):
                cls._deep_merge_keep_existing(existing, incoming)
                continue

            if isinstance(existing, list) and isinstance(incoming, list):
                if len(existing) == 0 and len(incoming) > 0:
                    base[key] = incoming
                continue

            if cls._is_empty_value(existing) and not cls._is_empty_value(incoming):
                base[key] = incoming

        return base

    @staticmethod
    def _dedup_append(existing: list[dict[str, Any]], new_items: list[dict[str, Any]], *, keys: tuple[str, ...]) -> None:
        seen = set()
        for item in existing:
            seen.add(tuple((item or {}).get(k) for k in keys))
        for item in new_items or []:
            fingerprint = tuple((item or {}).get(k) for k in keys)
            if fingerprint in seen:
                continue
            existing.append(item)
            seen.add(fingerprint)

    @staticmethod
    def _compact_state_for_prompt(data: dict[str, Any]) -> dict[str, Any]:
        """
        Remove large arrays to keep the prompt small; keep counts instead.
        """
        compact = deepcopy(data or {})

        thy = compact.get("thyrocare")
        if isinstance(thy, dict) and isinstance(thy.get("test_results"), list):
            compact.setdefault("thyrocare", {})
            compact["thyrocare"]["test_results_count"] = len(thy.get("test_results") or [])
            compact["thyrocare"].pop("test_results", None)

        sec = compact.get("second_medic")
        if isinstance(sec, dict) and isinstance(sec.get("diagnostics"), list):
            compact.setdefault("second_medic", {})
            compact["second_medic"]["diagnostics_count"] = len(sec.get("diagnostics") or [])
            compact["second_medic"].pop("diagnostics", None)

        return compact
    
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

    def extract_with_evidence_from_pdf_incremental(
        self,
        pdf_path: str | Path,
        use_ocr: bool = False,
        ocr_threshold: int = 100,
        dpi: int = 300,
        language: str = "eng",
        generate_inference: bool = True,
    ) -> IncrementalExtractionResult:
        """
        Incrementally extract fields page-by-page, keeping a compact structured state.

        This avoids sending OCR text for the entire document in a single LLM call,
        while maintaining continuity via a running structured state + summary.
        """
        pdf_path = Path(pdf_path)
        logger.info(f"Starting incremental extraction from PDF: {pdf_path.name}")

        current_data: dict[str, Any] = {
            "staff_details": {},
            "thyrocare": {},
            "second_medic": {},
            "inference": "",
        }
        running_summary = ""
        doc_type = DocumentType.UNKNOWN
        evidence: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []

        for page_number, page_text, method in self.document_loader.iter_pdf_pages_text(
            pdf_path,
            use_ocr=use_ocr,
            ocr_threshold=ocr_threshold,
            dpi=dpi,
            language=language,
        ):
            logger.info(
                f"LLM incremental pass on page {page_number} ({method}); page_text={len(page_text)} chars"
            )
            if not page_text.strip():
                continue

            compact_state = {
                "doc_type": doc_type.value,
                "data": self._compact_state_for_prompt(current_data),
            }

            update: IncrementalPageUpdate = self.page_update_chain.invoke(
                {
                    "current_state": json.dumps(compact_state, ensure_ascii=False),
                    "running_summary": running_summary,
                    "page_number": page_number,
                    "page_text": page_text,
                }
            )

            doc_type = update.doc_type or doc_type
            running_summary = update.running_summary or running_summary

            if isinstance(update.updates, dict) and update.updates:
                self._deep_merge_keep_existing(current_data, update.updates)

            # Append-only arrays (kept out of prompt for compactness)
            if update.new_test_results:
                thy = current_data.get("thyrocare")
                if not isinstance(thy, dict):
                    thy = {}
                    current_data["thyrocare"] = thy
                thy.setdefault("test_results", [])
                if isinstance(thy["test_results"], list):
                    self._dedup_append(
                        thy["test_results"],
                        update.new_test_results,
                        keys=("test_name", "value", "units"),
                    )

            if update.new_diagnostics:
                sec = current_data.get("second_medic")
                if not isinstance(sec, dict):
                    sec = {}
                    current_data["second_medic"] = sec
                sec.setdefault("diagnostics", [])
                if isinstance(sec["diagnostics"], list):
                    self._dedup_append(
                        sec["diagnostics"],
                        update.new_diagnostics,
                        keys=("test_category", "test_name", "impression"),
                    )

            evidence.extend([e.model_dump(mode="json") for e in (update.evidence or [])])
            conflicts.extend([c.model_dump(mode="json") for c in (update.conflicts or [])])

        if generate_inference:
            compact_for_inference = {
                "doc_type": doc_type.value,
                "data": self._compact_state_for_prompt(current_data),
            }
            inference_obj: InferenceOnly = self.inference_chain.invoke(
                {
                    "structured_state": json.dumps(compact_for_inference, ensure_ascii=False),
                    "running_summary": running_summary,
                }
            )
            current_data["inference"] = inference_obj.inference.strip()

        data = MedicalReportData.model_validate(current_data)
        logger.info("Incremental extraction completed successfully")

        return IncrementalExtractionResult(
            doc_type=doc_type,
            data=data,
            running_summary=running_summary,
            evidence=evidence,
            conflicts=conflicts,
        )

    def extract_from_pdf_incremental(
        self,
        pdf_path: str | Path,
        use_ocr: bool = False,
        ocr_threshold: int = 100,
        dpi: int = 300,
        language: str = "eng",
        generate_inference: bool = True,
    ) -> MedicalReportData:
        """
        Convenience wrapper that returns only MedicalReportData.
        """
        result = self.extract_with_evidence_from_pdf_incremental(
            pdf_path=pdf_path,
            use_ocr=use_ocr,
            ocr_threshold=ocr_threshold,
            dpi=dpi,
            language=language,
            generate_inference=generate_inference,
        )
        return result.data
    
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
