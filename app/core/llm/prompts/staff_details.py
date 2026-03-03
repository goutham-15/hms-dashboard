from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import PromptTemplate
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

Format Instructions:
{format_instructions}
"""

PROMPT = PromptTemplate(
    template=prompt_template,
    input_variables=["context"],
    partial_variables={"format_instructions": parser.get_format_instructions()},
)
