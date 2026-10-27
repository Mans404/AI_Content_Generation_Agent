from pydantic import BaseModel

from src.models.companies import CompanyLanguage, CompanyIndustry


class CompanyDataResponse(BaseModel):
    company_name: str
    industry: str
    yourPicture_filename: str
    yourPicture_size: int
    language: CompanyLanguage
    audiences: list[str]
    posts_per_week: int