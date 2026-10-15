from pydantic import BaseModel


class CompanyDataResponse(BaseModel):
    company_name: str
    industry: str
    reference_design_filename: str
    reference_design_size: int