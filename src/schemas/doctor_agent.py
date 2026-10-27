from uuid import UUID

from pydantic import BaseModel


class DoctorContext(BaseModel):
    doctor_id: UUID
    doctor_name: str
    doctor_specialization: str
    picture_path: str


class AgentOutput(BaseModel):
    ideas: list[str]
    post_types: list[str]
    doctor_theme: str