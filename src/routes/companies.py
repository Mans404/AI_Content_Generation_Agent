from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile, status
from pydantic import StringConstraints

from src.controllers.companies import create_companies
from src.models.companies import DoctorLanguage, DoctorSpecialization
from src.schemas.companies import DoctorDataResponse


companies_router = APIRouter(
    prefix="/api/v1/companies",
    tags=["api_v1", "companies"],
)

MAX_LIST_ITEMS = 20
MAX_POSTS_PER_WEEK = 21  # adjust to your business rule

DoctorName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]

DoctorProfileItem = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]


@companies_router.post(
    "/",
    response_model=DoctorDataResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_companies_route(
    doctor_name: DoctorName = Form(...),
    doctor_specialization: DoctorSpecialization = Form(DoctorSpecialization.OTHER),
    yourPicture: UploadFile = File(...),
    language: DoctorLanguage = Form(DoctorLanguage.EN),
    audiences: list[DoctorProfileItem] = Form([], max_length=MAX_LIST_ITEMS),
    types_of_medical_procedures: list[DoctorProfileItem] = Form(
        [], max_length=MAX_LIST_ITEMS
    ),
    doctor_offers: list[DoctorProfileItem] = Form([], max_length=MAX_LIST_ITEMS),
    advice_and_matters_that_most_people_find_confusing: list[DoctorProfileItem] = Form(
        [], max_length=MAX_LIST_ITEMS
    ),
    strengths: list[DoctorProfileItem] = Form([], max_length=MAX_LIST_ITEMS),
    posts_per_week: int = Form(3, ge=1, le=MAX_POSTS_PER_WEEK),
) -> DoctorDataResponse:

    return await create_companies(
        doctor_name=doctor_name,
        doctor_specialization=doctor_specialization,
        yourPicture=yourPicture,
        language=language,
        audiences=audiences,
        types_of_medical_procedures=types_of_medical_procedures,
        doctor_offers=doctor_offers,
        advice_and_matters_that_most_people_find_confusing=(
            advice_and_matters_that_most_people_find_confusing
        ),
        strengths=strengths,
        posts_per_week=posts_per_week,
    )