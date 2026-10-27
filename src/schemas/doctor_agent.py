from uuid import UUID

from pydantic import BaseModel

from src.models.companies import DoctorLanguage, DoctorSpecialization


class DoctorContext(BaseModel):
    doctor_id: UUID
    doctor_name: str
    doctor_specialization: DoctorSpecialization
    language: DoctorLanguage
    picture_path: str
    audiences: list[str]
    types_of_medical_procedures: list[str]
    doctor_offers: list[str]
    advice_and_matters_that_most_people_find_confusing: list[str]
    strengths: list[str]
    posts_per_week: int


class AgentOutput(BaseModel):
    ideas: list[str]
    post_types: list[str]
    doctor_theme: str