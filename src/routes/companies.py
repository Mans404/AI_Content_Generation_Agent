from fastapi import APIRouter, File, Form, UploadFile, status

from src.controllers.companies import create_companies
from src.models.companies import CompanyLanguage, CompanyIndustry
from src.schemas.companies import CompanyDataResponse


companies_router = APIRouter(
    prefix="/api/v1/companies",
    tags=["api_v1", "companies"],
)


@companies_router.post(
    "/",
    response_model=CompanyDataResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_companies_route(
    company_name: str = Form(..., min_length=1),
    industry: CompanyIndustry = Form(CompanyIndustry.OTHER), # Previously tone
    yourPicture: UploadFile = File(...),
    language: CompanyLanguage = Form(CompanyLanguage.EN),
    audiences: list[str] = Form([]),
    posts_per_week: int = Form(3, ge=1),
) -> CompanyDataResponse:

    return await create_companies(
        company_name=company_name, # Doctor Name
        industry=industry,
        yourPicture=yourPicture,
        language=language,
        audiences=audiences,
        posts_per_week=posts_per_week,
    )