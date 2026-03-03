from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from app.models.medical_report import SecondMedic


parser = PydanticOutputParser(pydantic_object=SecondMedic)

prompt_template = """
You are an expert at extracting information from medical reports, specifically from SecondMedic diagnostic reports.
Your task is to extract the findings and impressions from imaging and diagnostic reports.

Context:
{context}

Please extract the information for the following report types:
- USG Abdomen
- Echocardiogram
- Chest X-Ray
- ECG

For each report type, extract the 'findings' and 'impression'.
Format the output according to the following schema.
If a report type is not mentioned in the context, leave it out of the output.

Format Instructions:
{format_instructions}
"""

PROMPT = PromptTemplate(
    template=prompt_template,
    input_variables=["context"],
    partial_variables={"format_instructions": parser.get_format_instructions()},
)
