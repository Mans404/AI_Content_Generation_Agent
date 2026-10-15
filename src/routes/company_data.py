from fastapi import APIRouter, File, Form, UploadFile, status

from src.controllers.company_data import create_company_data
from src.schemas.company_data import CompanyDataResponse


company_data_router = APIRouter(
    prefix="/api/v1/company_data",
    tags=["api_v1", "company_data"],
)


@company_data_router.post(
    "/",
    response_model=CompanyDataResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_company_data_route(
    company_name: str = Form(..., min_length=1),
    industry: str = Form(..., min_length=1),
    reference_design: UploadFile = File(...),
) -> CompanyDataResponse:

    return await create_company_data(
        company_name=company_name,
        industry=industry,
        reference_design=reference_design,
    )