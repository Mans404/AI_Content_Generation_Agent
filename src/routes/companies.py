from fastapi import APIRouter, File, Form, UploadFile, status

from src.controllers.companies import create_companies
from src.models.companies import DoctorLanguage, DoctorSpecialization
from src.schemas.companies import DoctorDataResponse


companies_router = APIRouter(
    prefix="/api/v1/companies",
    tags=["api_v1", "companies"],
)


@companies_router.post(
    "/",
    response_model=DoctorDataResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_companies_route(
    doctor_name: str = Form(..., min_length=1),
    doctor_specialization: DoctorSpecialization = Form(DoctorSpecialization.OTHER), # Previously tone
    yourPicture: UploadFile = File(...),
    language: DoctorLanguage = Form(DoctorLanguage.EN),
    audiences: list[str] = Form([]),
    posts_per_week: int = Form(3, ge=1),
) -> DoctorDataResponse:

    return await create_companies(
        doctor_name=doctor_name,
        doctor_specialization=doctor_specialization,
        yourPicture=yourPicture,
        language=language,
        audiences=audiences,
        posts_per_week=posts_per_week,
    )