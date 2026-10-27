from pydantic import BaseModel

from src.models.companies import DoctorLanguage, DoctorSpecialization


class DoctorDataResponse(BaseModel):
    doctor_name: str
    doctor_specialization: str
    yourPicture_filename: str
    yourPicture_size: int
    language: DoctorLanguage
    audiences: list[str]
    posts_per_week: int