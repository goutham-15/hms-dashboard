import operator
from typing import List, TypedDict, Optional, Dict, Annotated
import json

from langchain_aws.chat_models import ChatBedrock
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, ValidationError

from app.core.llm.prompts import staff_details, thyrocare_details, second_medic_details, health_inference
from app.core.vector_db import VectorDB
from app.models.medical_report import StaffDetails, Thyrocare, SecondMedic, FacultyHealthProfile, CostDetails
from app.db.staff_master import StaffMasterDB
from app.utils.logger import get_logger


def _join_context(chunks: list[str], *, max_chars: int = 4000) -> str:
    buf: list[str] = []
    total = 0
    for c in chunks:
        if not c:
            continue
        if total + len(c) + 2 > max_chars:
            break
        buf.append(c)
        total += len(c) + 2
    return "\n\n".join(buf)


class GraphState(TypedDict):
    """
    Represents the state of our graph.
    """
    full_text: str
    source_id: Optional[str]
    report_type_chunks: Dict[str, List[str]]
    staff_context: Optional[str]
    staff_details: Optional[StaffDetails]
    thyrocare_details: Optional[Thyrocare]
    secondmedic_details: Optional[SecondMedic]
    health_inference: Optional[Dict]
    final_summary: Optional[FacultyHealthProfile]
    input_tokens: Annotated[int, operator.add]
    output_tokens: Annotated[int, operator.add]


class MedicalReportExtractor:
    def __init__(self, llm: ChatBedrock, vector_db: VectorDB):
        self.llm = llm
        self.vector_db = vector_db
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Builds the langgraph extraction workflow."""
        graph = StateGraph(GraphState)

        graph.add_node("retrieve_chunks", self.retrieve_filtered_chunks)
        graph.add_node("extract_staff", self.extract_staff_details)
        graph.add_node("extract_thyrocare", self.extract_thyrocare_details)
        graph.add_node("extract_secondmedic", self.extract_secondmedic_details)
        graph.add_node("generate_inference", self.generate_health_inference)
        graph.add_node("combine_results", self.combine_results)

        graph.set_entry_point("retrieve_chunks")
        graph.add_edge("retrieve_chunks", "extract_staff")
        graph.add_edge("retrieve_chunks", "extract_thyrocare")
        graph.add_edge("retrieve_chunks", "extract_secondmedic")
        
        graph.add_edge("extract_staff", "generate_inference")
        graph.add_edge("extract_thyrocare", "generate_inference")
        graph.add_edge("extract_secondmedic", "generate_inference")
        
        graph.add_edge("generate_inference", "combine_results")
        graph.add_edge("combine_results", END)

        return graph.compile()

    def extract(self, full_text: str, *, source_id: Optional[str] = None) -> FacultyHealthProfile:
        inputs = {
            "full_text": full_text, 
            "source_id": source_id, 
            "report_type_chunks": {}, 
            "staff_context": None,
            "input_tokens": 0,
            "output_tokens": 0
        }
        result = self.graph.invoke(inputs)
        return result.get("final_summary", FacultyHealthProfile())

    def retrieve_filtered_chunks(self, state: GraphState) -> Dict:
        """Retrieves document chunks filtered by report type."""
        source_id = state.get("source_id")

        def _get_docs(where: dict) -> list[str]:
            got = self.vector_db.get(where=where, include=["documents", "metadatas"])
            docs = got.get("documents") or []
            metas = got.get("metadatas") or []
            rows: list[tuple[str, dict]] = []
            for d, m in zip(docs, metas):
                if (d or "").strip():
                    rows.append((d or "", m or {}))
            rows.sort(
                key=lambda r: (
                    int(r[1].get("page_in_report", 0) or 0),
                    int(r[1].get("page", 0) or 0),
                )
            )
            return [d for d, _ in rows]

        base: dict = {}
        if source_id:
            base["source_id"] = source_id

        thy_docs = _get_docs({**base, "report_type": "thyrocare"})
        second_docs = _get_docs({**base, "report_type": "second_medic"})

        # Get ONLY the first chunk of the SecondMedic report for staff identity
        staff_chunks: list[str] = []
        first_sm = _get_docs({**base, "report_type": "second_medic", "page_in_report": 1})
        if first_sm:
            staff_chunks.append(first_sm[0])
        
        return {
            "report_type_chunks": {"thyrocare": thy_docs, "second_medic": second_docs},
            "staff_context": _join_context(staff_chunks, max_chars=2000)
        }

    def _get_token_usage(self, response) -> tuple[int, int]:
        """Extracts token usage from Bedrock response metadata."""
        try:
            usage = response.response_metadata.get("usage", {})
            return usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
        except:
            return 0, 0

    def _clean_llm_response(self, response) -> str:
        """
        Clean LLM response to extract only the JSON part.
        Removes explanatory text, code blocks, and JavaScript-style comments that break JSON parsing.
        """
        import re
        
        # Get the text content from the response
        if hasattr(response, 'content'):
            text = response.content
        else:
            text = str(response)
        
        # Remove markdown code blocks if present
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        
        # Try to extract JSON from the response
        # Look for content between first { and last }
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            
            # Remove JavaScript-style comments (// ...) that break JSON
            # This handles both inline and end-of-line comments
            json_str = re.sub(r'//[^\n]*', '', json_str)
            
            # Remove multi-line comments (/* ... */)
            json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)
            
            # Clean up any trailing commas before closing braces/brackets
            json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
            
            return json_str
        
        return text

    def extract_staff_details(self, state: GraphState) -> Dict:
        """
        Extracts staff details in 3 parts:
        1. Extract staff ID, name, age, gender, screening date from document using REGEX (not LLM).
        2. Get department from the staff_master table using the extracted ID.
        3. Return the complete staff details.
        """
        logger = get_logger(name="extraction")
        from app.core.regex_extraction import extract_staff_details_from_text
        from app.db.staff_master import StaffMasterDB
        
        staff_master_db = StaffMasterDB()
        
        # Context: First chunk of SecondMedic report (per requirement)
        context = (state.get("staff_context") or "").strip()
        if not context:
            full_text = state.get("full_text", "")
            context = full_text[:2000] if full_text else ""
            
        # Part 1: REGEX Extraction (Identity + Screening Info)
        logger.info("Part 1: REGEX extracting ID, name, age, gender, date from document...")
        final_staff = extract_staff_details_from_text(context)
        
        # Part 2: Database Lookup for Department
        if final_staff.employee_id:
            logger.info(f"Part 2: Fetching department from Staff Master DB for ID '{final_staff.employee_id}'...")
            db_details = staff_master_db.get_staff_details(final_staff.employee_id)
            
            if db_details and db_details.department:
                final_staff.department = db_details.department
                logger.info(f"Department from DB: {final_staff.department}")
            else:
                logger.warning(f"ID '{final_staff.employee_id}' not found in DB. Setting Department to 'Others'.")
                final_staff.department = "Others"
        else:
            logger.warning("No Employee ID found. Setting Department to 'Others'.")
            final_staff.department = "Others"
        
        logger.info(f"Final Staff Details: {final_staff.employee_id} | {final_staff.name} | {final_staff.age} | {final_staff.gender} | {final_staff.department}")
        
        return {
            "staff_details": final_staff,
            "input_tokens": 0,  # No LLM used for staff extraction
            "output_tokens": 0
        }

    def extract_thyrocare_details(self, state: GraphState) -> Dict:
        """Extracts Thyrocare details from filtered chunks."""
        context = _join_context(state["report_type_chunks"].get("thyrocare", []))
        if not context:
            return {"thyrocare_details": Thyrocare(), "input_tokens": 0, "output_tokens": 0}

        chain = thyrocare_details.PROMPT | self.llm
        response = chain.invoke({"context": context})
        
        # Clean the response before parsing
        cleaned_response_text = self._clean_llm_response(response)
        
        try:
            json_data = json.loads(cleaned_response_text)
            extracted = Thyrocare(**json_data)
        except (json.JSONDecodeError, ValidationError) as e:
            logger = get_logger(name="extraction")
            logger.warning(f"Failed to parse thyrocare details: {e}. Using defaults.")
            extracted = Thyrocare()
        
        in_tokens, out_tokens = self._get_token_usage(response)
        
        return {
            "thyrocare_details": extracted,
            "input_tokens": in_tokens,
            "output_tokens": out_tokens
        }

    def extract_secondmedic_details(self, state: GraphState) -> Dict:
        """Extracts SecondMedic details from filtered chunks."""
        context = _join_context(state["report_type_chunks"].get("second_medic", []))
        if not context:
            return {"secondmedic_details": SecondMedic(), "input_tokens": 0, "output_tokens": 0}

        chain = second_medic_details.PROMPT | self.llm
        response = chain.invoke({"context": context})
        
        # Clean the response before parsing
        cleaned_response_text = self._clean_llm_response(response)
        
        try:
            json_data = json.loads(cleaned_response_text)
            extracted = SecondMedic(**json_data)
        except (json.JSONDecodeError, ValidationError) as e:
            logger = get_logger(name="extraction")
            logger.warning(f"Failed to parse secondmedic details: {e}. Using defaults.")
            extracted = SecondMedic()
        
        in_tokens, out_tokens = self._get_token_usage(response)
        
        return {
            "secondmedic_details": extracted,
            "input_tokens": in_tokens,
            "output_tokens": out_tokens
        }

    def generate_health_inference(self, state: GraphState) -> Dict:
        """Generates a consolidated medical summary using the extracted data."""
        thyrocare = state.get("thyrocare_details") or Thyrocare()
        secondmedic = state.get("secondmedic_details") or SecondMedic()
        staff = state.get("staff_details") or StaffDetails()

        chain = health_inference.PROMPT | self.llm
        response = chain.invoke({
            "thyrocare_json": thyrocare.model_dump_json(),
            "secondmedic_json": secondmedic.model_dump_json(),
            "staff_details_json": staff.model_dump_json()
        })
        
        # Clean the response before parsing
        cleaned_response_text = self._clean_llm_response(response)
        
        try:
            result = json.loads(cleaned_response_text)
        except json.JSONDecodeError as e:
            logger = get_logger(name="extraction")
            logger.warning(f"Failed to parse health inference: {e}. Using defaults.")
            result = {
                "inference": "",
                "active_flags": [],
                "status": "Unknown",
                "suggestion": [],
                "overall_health_score": 0
            }
        
        in_tokens, out_tokens = self._get_token_usage(response)
        
        return {
            "health_inference": result,
            "input_tokens": in_tokens,
            "output_tokens": out_tokens
        }

    def combine_results(self, state: GraphState) -> Dict:
        """Combines all extracted data into a final profile."""
        inf = state.get("health_inference") or {}
        staff = state.get("staff_details") or StaffDetails()
        
        # Update staff details with health score from inference
        staff.overall_health_score = inf.get("overall_health_score", 0)
        
        # Calculate cost: $0.15 per 1M tokens for both input and output (placeholder for Llama 3.2 3B)
        input_tokens = state.get("input_tokens", 0)
        output_tokens = state.get("output_tokens", 0)
        total_cost = (input_tokens + output_tokens) * (0.15 / 1_000_000)
        
        cost_details = CostDetails(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=round(total_cost, 6)
        )
        
        final_summary = FacultyHealthProfile(
            staff_details=staff,
            thyrocare=state.get("thyrocare_details") or Thyrocare(),
            secondmedic=state.get("secondmedic_details") or SecondMedic(),
            inference=inf.get("inference", ""),
            active_flags=inf.get("active_flags", []),
            status=inf.get("status", ""),
            suggestion=inf.get("suggestion", []),
            cost=cost_details
        )
        return {"final_summary": final_summary}
