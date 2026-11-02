from datetime import datetime

from pydantic import BaseModel, Field

from src.models.companies import DoctorLanguage, DoctorSpecialization
from src.schemas.doctor_agent import AgentOutput


class DoctorDataResponse(BaseModel):
    doctor_name: str
    doctor_specialization: str
    yourPicture_filename: str
    yourPicture_size: int
    language: DoctorLanguage
    audiences: list[str]
    types_of_medical_procedures: list[str]
    strengths: list[str]
    posts_per_week: int
    agent_output: AgentOutput


class MonthlyIdeasRequest(BaseModel):
    doctor_offers: list[str] = Field(default_factory=list, max_length=10)
    advice_and_matters_that_most_people_find_confusing: list[str] = Field(
        default_factory=list,
        max_length=10,
    )


class MonthlyIdeasResponse(MonthlyIdeasRequest):
    month_start: datetime


class StartPlanningResponse(MonthlyIdeasResponse):
    agent_output: AgentOutput