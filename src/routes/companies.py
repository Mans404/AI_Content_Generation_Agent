from fastapi import APIRouter, File, Form, UploadFile, status

from src.controllers.companies import create_companies
from src.models.companies import CompanyLanguage, CompanyTone
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
    industry: str = Form(..., min_length=1),
    reference_design: UploadFile = File(...),
    language: CompanyLanguage = Form(CompanyLanguage.EN),
    primary_color: str = Form("#000000", min_length=1),
    secondary_color: str = Form("#FFFFFF", min_length=1),
    tone: CompanyTone = Form(CompanyTone.PROFESSIONAL),
    audiences: list[str] = Form([]),
    posts_per_week: int = Form(3, ge=1),
) -> CompanyDataResponse:

    return await create_companies(
        company_name=company_name,
        industry=industry,
        reference_design=reference_design,
        language=language,
        primary_color=primary_color,
        secondary_color=secondary_color,
        tone=tone,
        audiences=audiences,
        posts_per_week=posts_per_week,
    )