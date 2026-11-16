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
    upcoming_occasions: list[str] = Field(default_factory=list)


class AgentOutput(BaseModel):
    ideas: list[str]
    post_types: list[str]

    @model_validator(mode="after")
    def validate_post_counts(self, info: ValidationInfo) -> "AgentOutput":
        posts_per_week = info.context.get("posts_per_week") if info.context else None

        if posts_per_week is not None:
            expected_count = posts_per_week * 4

            
            self.ideas = self.ideas[:expected_count]
            self.post_types = self.post_types[:expected_count]

            if len(self.ideas) < expected_count or len(self.post_types) < expected_count:
                raise ValueError(
                    "ideas and post_types must each contain "
                    f"{expected_count} items for {posts_per_week} posts per week"
                )

        if len(self.ideas) != len(self.post_types):
            raise ValueError("ideas and post_types must have the same length")

        return self


class DesignPromptOutput(BaseModel):
    design_prompts: list[str]

    @model_validator(mode="after")
    def validate_prompt_count(self) -> "DesignPromptOutput":
        if not self.design_prompts:
            raise ValueError("design_prompts must contain at least one prompt")
        return self


class CaptionOutput(BaseModel):
    captions: list[str]

    @model_validator(mode="after")
    def validate_captions(self) -> "CaptionOutput":
        if not self.captions:
            raise ValueError("captions must contain at least one caption")
        return self