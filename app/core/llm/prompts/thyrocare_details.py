from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from app.models.medical_report import Thyrocare


parser = PydanticOutputParser(pydantic_object=Thyrocare)

prompt_template = """
You are an expert at extracting information from medical reports, specifically from Thyrocare lab results.
Your task is to extract all the biochemical lab test data from the provided context.

Context:
{context}

Please extract the information for the following test groups:
- Diabetes Panel
- Lipid Profile
- Renal/Kidney Function
- Vitamins & Hormones
- Liver Function

For each test, extract the name, value, unit, reference range, and status.
Format the output according to the following schema.
If a test group or a specific test is not mentioned, leave it out of the output.
Each test group (e.g., Diabetes Panel) is a list of results.

Format Instructions:
{format_instructions}
"""

PROMPT = PromptTemplate(
    template=prompt_template,
    input_variables=["context"],
    partial_variables={"format_instructions": parser.get_format_instructions()},
)
