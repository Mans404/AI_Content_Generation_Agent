from typing import Annotated

from fastapi import APIRouter, File, Form, Response, UploadFile, status
from pydantic import StringConstraints

from src.controllers.companies import (
    create_or_update_company,
    create_or_update_monthly_ideas,
    start_planning,
)
from src.jwt.auth import CurrentUser
from src.models.companies import DoctorLanguage, DoctorSpecialization
from src.schemas.companies import (
    DoctorDataResponse,
    MonthlyIdeasRequest,
    MonthlyIdeasResponse,
    StartPlanningResponse,
)


companies_router = APIRouter(
    prefix="/api/v1/companies",
    tags=["companies"],
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
)
async def create_companies_route(
    current_user: CurrentUser,
    response: Response,
    doctor_name: DoctorName = Form(...),
    doctor_specialization: DoctorSpecialization = Form(DoctorSpecialization.OTHER),
    yourPicture: UploadFile | None = File(None),
    language: DoctorLanguage = Form(DoctorLanguage.EN),
    audiences: list[DoctorProfileItem] = Form([], max_length=MAX_LIST_ITEMS),
    types_of_medical_procedures: list[DoctorProfileItem] = Form(
        [], max_length=MAX_LIST_ITEMS
    ),
    strengths: list[DoctorProfileItem] = Form([], max_length=MAX_LIST_ITEMS),
    posts_per_week: int = Form(3, ge=1, le=MAX_POSTS_PER_WEEK),
) -> DoctorDataResponse:

    doctor_response, created = await create_or_update_company(
        owner_id=current_user.id,
        doctor_name=doctor_name,
        doctor_specialization=doctor_specialization,
        yourPicture=yourPicture,
        language=language,
        audiences=audiences,
        types_of_medical_procedures=types_of_medical_procedures,
        strengths=strengths,
        posts_per_week=posts_per_week,
    )
    response.status_code = (
        status.HTTP_201_CREATED if created else status.HTTP_200_OK
    )
    return doctor_response


@companies_router.post(
    "/monthly-ideas",
    response_model=MonthlyIdeasResponse,
)
async def create_monthly_ideas_route(
    current_user: CurrentUser,
    monthly_ideas: MonthlyIdeasRequest,
) -> MonthlyIdeasResponse:
    return await create_or_update_monthly_ideas(
        owner_id=current_user.id,
        doctor_offers=monthly_ideas.doctor_offers,
        advice_and_matters_that_most_people_find_confusing=(
            monthly_ideas.advice_and_matters_that_most_people_find_confusing
        ),
    )


@companies_router.post(
    "/start_planning",
    response_model=StartPlanningResponse,
)
async def start_planning_route(
    current_user: CurrentUser,
) -> StartPlanningResponse:
    return await start_planning(owner_id=current_user.id)