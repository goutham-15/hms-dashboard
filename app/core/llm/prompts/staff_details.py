from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from app.models.medical_report import StaffDetails


parser = PydanticOutputParser(pydantic_object=StaffDetails)

prompt_template = """
You are an expert at extracting information from medical reports.
Your task is to extract the staff member's personal and employment details from the provided context.

Context:
{context}

Please extract the information and format it according to the following schema.
Make sure to follow the data types and constraints exactly.
If a field is not available in the context, use the default value or an empty string.

CRITICAL REQUIREMENTS: 
1. Sometimes the employee ID and the name appear concatenated together in the source text (e.g., "[ID] [Name]"). Separate them.
2. If the "Department" is not explicitly mentioned, try to infer it from the `employee_id` prefix or code if possible (e.g., "ME" or "MECH" for Mechanical, "IT" for Information Technology, "CS" for Computer Science).
3. **DATE FORMAT**: The screening_date field MUST be in YYYY-MM-DD format (e.g., "2024-01-29", "2025-03-15"). 
   - If you see dates like "29/1/2024" or "29/1", convert them to "2024-01-29" format.
   - If the year is missing, use the current year (2026).
   - If the date is incomplete or unclear, use "2026-01-01" as a fallback.
4. **JSON OUTPUT**: Return ONLY valid JSON without any comments, explanations, or additional text.
   - DO NOT include comments like "// inferred from..." in the JSON output.
   - DO NOT add any text before or after the JSON.

Format Instructions:
{format_instructions}
"""

PROMPT = PromptTemplate(
    template=prompt_template,
    input_variables=["context"],
    partial_variables={"format_instructions": parser.get_format_instructions()},
)
