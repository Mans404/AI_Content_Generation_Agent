from pydantic import BaseModel

from src.models.companies import DoctorLanguage, DoctorSpecialization


class DoctorDataResponse(BaseModel):
    doctor_name: str
    doctor_specialization: str
    yourPicture_filename: str
    yourPicture_size: int
    language: DoctorLanguage
    audiences: list[str]
    types_of_medical_procedures: list[str]
    doctor_offers: list[str]
    advice_and_matters_that_most_people_find_confusing: list[str]
    strengths: list[str]
    posts_per_week: int