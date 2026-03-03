from typing import List, TypedDict, Optional, Dict

from langchain_aws.chat_models import ChatBedrock
from langgraph.graph import StateGraph, END
from pydantic import BaseModel

from app.core.llm.prompts import staff_details, thyrocare_details, second_medic_details
from app.core.vector_db import VectorDB
from app.models.medical_report import StaffDetails, Thyrocare, SecondMedic, FacultyHealthProfile


def _join_context(chunks: list[str], *, max_chars: int = 12000) -> str:
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
    report_type_chunks: Dict[str, List[str]]
    staff_details: Optional[StaffDetails]
    thyrocare_details: Optional[Thyrocare]
    secondmedic_details: Optional[SecondMedic]
    final_summary: Optional[FacultyHealthProfile]


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
        graph.add_node("combine_results", self.combine_results)

        graph.set_entry_point("retrieve_chunks")
        graph.add_edge("retrieve_chunks", "extract_staff")
        graph.add_edge("extract_staff", "extract_thyrocare")
        graph.add_edge("extract_thyrocare", "extract_secondmedic")
        graph.add_edge("extract_secondmedic", "combine_results")
        graph.add_edge("combine_results", END)

        return graph.compile()

    def extract(self, full_text: str) -> FacultyHealthProfile:
        """
        Runs the extraction graph.
        """
        inputs = {"full_text": full_text, "report_type_chunks": {}}
        result = self.graph.invoke(inputs)
        return result.get("final_summary", FacultyHealthProfile())

    def retrieve_filtered_chunks(self, state: GraphState) -> GraphState:
        """Retrieves document chunks filtered by report type."""
        thyrocare_docs = self.vector_db.similarity_search(query="thyrocare", filter={"report_type": "thyrocare"}, k=20)
        secondmedic_docs = self.vector_db.similarity_search(query="secondmedic", filter={"report_type": "second_medic"}, k=20)

        state["report_type_chunks"] = {
            "thyrocare": [doc.page_content for doc in thyrocare_docs],
            "second_medic": [doc.page_content for doc in secondmedic_docs],
        }
        return state

    def extract_staff_details(self, state: GraphState) -> GraphState:
        """Extracts staff details from the full text."""
        chain = staff_details.PROMPT | self.llm | staff_details.parser
        extracted = chain.invoke({"context": state["full_text"]})
        state["staff_details"] = extracted
        return state

    def extract_thyrocare_details(self, state: GraphState) -> GraphState:
        """Extracts Thyrocare details from filtered chunks."""
        context = _join_context(state["report_type_chunks"].get("thyrocare", []))
        if not context:
            state["thyrocare_details"] = Thyrocare()
            return state

        chain = thyrocare_details.PROMPT | self.llm | thyrocare_details.parser
        extracted = chain.invoke({"context": context})
        state["thyrocare_details"] = extracted
        return state

    def extract_secondmedic_details(self, state: GraphState) -> GraphState:
        """Extracts SecondMedic details from filtered chunks."""
        context = _join_context(state["report_type_chunks"].get("second_medic", []))
        if not context:
            state["secondmedic_details"] = SecondMedic()
            return state

        chain = second_medic_details.PROMPT | self.llm | second_medic_details.parser
        extracted = chain.invoke({"context": context})
        state["secondmedic_details"] = extracted
        return state

    def combine_results(self, state: GraphState) -> GraphState:
        """Combines all extracted data into a final profile."""
        state["final_summary"] = FacultyHealthProfile(
            staff_details=state.get("staff_details") or StaffDetails(),
            thyrocare=state.get("thyrocare_details") or Thyrocare(),
            secondmedic=state.get("secondmedic_details") or SecondMedic(),
        )
        return state
