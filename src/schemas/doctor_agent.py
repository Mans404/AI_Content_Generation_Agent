from uuid import UUID

from pydantic import BaseModel, Field, ValidationInfo, model_validator

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
    posts_per_week: int = Field(..., ge=1, le=21)


class AgentOutput(BaseModel):
    ideas: list[str]
    post_types: list[str]

    @model_validator(mode="after")
    def validate_post_counts(self, info: ValidationInfo) -> "AgentOutput":
        if len(self.ideas) != len(self.post_types):
            raise ValueError("ideas and post_types must have the same length")

        posts_per_week = info.context.get("posts_per_week") if info.context else None
        if posts_per_week is not None:
            expected_count = posts_per_week * 4
            if len(self.ideas) != expected_count:
                raise ValueError(
                    "ideas and post_types must each contain "
                    f"{expected_count} items for {posts_per_week} posts per week"
                )

        return self