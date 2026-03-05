from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from typing import List

class InferenceOutput(BaseModel):
    inference: str = Field(description="Consolidated medical summary.")
    active_flags: List[str] = Field(description="List of key flagged conditions.")
    status: str = Field(description="Overall health risk category.")
    suggestion: List[str] = Field(description="Actionable medical or lifestyle recommendations.")
    overall_health_score: int = Field(description="A numerical health score from 0 to 100 based on all available data.")

parser = JsonOutputParser(pydantic_object=InferenceOutput)

prompt_template = """
You are a senior medical consultant. Your task is to provide a consolidated health summary and risk assessment based on a patient's lab results and imaging findings.

Input Data:
Thyrocare Lab Results:
{thyrocare_json}

SecondMedic Imaging Findings:
{secondmedic_json}

Staff Details:
{staff_details_json}

Please provide the following:
1. Inference: A clear, concise clinical summary of the overall health status.
2. Active Flags: A list of key health concerns or flagged conditions (e.g., "High Cholesterol", "Fatty Liver").
3. Status: A single risk category from: "Critical", "High Risk", "Moderate Risk", "Healthy".
4. Suggestions: A list of actionable medical or lifestyle recommendations.
5. Overall Health Score: A numerical health score from 0 to 100 based on all available data. 100 is perfectly healthy, 0 is critical.

CRITICAL: Return ONLY valid JSON without any comments, explanations, or additional text.
- DO NOT include comments like "// inferred from..." in the JSON output.
- DO NOT add any text before or after the JSON.

Format Instructions:
{format_instructions}
"""

PROMPT = PromptTemplate(
    template=prompt_template,
    input_variables=["thyrocare_json", "secondmedic_json", "staff_details_json"],
    partial_variables={"format_instructions": parser.get_format_instructions()},
)
