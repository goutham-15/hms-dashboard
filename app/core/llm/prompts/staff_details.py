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
1. **EMPLOYEE ID & NAME**: Sometimes the employee ID and the name appear concatenated together in the source text (e.g., "[ID] [Name]"). Separate them carefully.
   - Extract ONLY the ID part for employee_id field
   - Extract ONLY the name part for name field

2. **GENDER EXTRACTION**: This is CRITICAL - DO NOT miss the gender field!
   - Look for explicit gender indicators: "Male", "Female", "M", "F", "MALE", "FEMALE"
   - Gender may appear in format like "29Y/M" (29 years Male) or "52Y/F" (52 years Female)
   - If you see "M" or "/M" anywhere, gender is "Male"
   - If you see "F" or "/F" anywhere, gender is "Female"
   - Common patterns: "Age 29 Gender FEMALE", "52Y/M", "29/M", etc.
   - ALWAYS extract gender if it exists in the text

3. **DEPARTMENT**: If not explicitly mentioned, try to infer from the employee_id prefix or job title
   - Examples: "ME"/"MECH" = Mechanical, "IT" = Information Technology, "CS" = Computer Science
   - Job titles like "Radiologist" = RADIOLOGY, "Consultant" = STAFF

4. **DATE FORMAT**: The screening_date field MUST be in YYYY-MM-DD format (e.g., "2024-01-29", "2025-03-15")
   - If you see dates like "29/12/2025" convert to "2025-12-29"
   - If you see "7 Jan, 2026" convert to "2026-01-07"
   - If the year is missing, use the current year (2026)
   - If the date is incomplete or unclear, use "2026-01-01" as a fallback

5. **JSON OUTPUT**: Return ONLY valid JSON without any comments, explanations, or additional text
   - DO NOT include comments like "// inferred from..." in the JSON output
   - DO NOT add any text before or after the JSON
   - DO NOT add "Note:" or explanations after the JSON

Format Instructions:
{format_instructions}
"""

PROMPT = PromptTemplate(
    template=prompt_template,
    input_variables=["context"],
    partial_variables={"format_instructions": parser.get_format_instructions()},
)
