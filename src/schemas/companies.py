from pydantic import BaseModel

from src.models.companies import CompanyLanguage, CompanyTone


class CompanyDataResponse(BaseModel):
    company_name: str
    industry: str
    reference_design_filename: str
    reference_design_size: int
    language: CompanyLanguage
    primary_color: str
    secondary_color: str
    tone: CompanyTone
    audiences: list[str]
    posts_per_week: int