from datetime import datetime
from typing import Literal
from uuid import UUID

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


class DesignPromptsResponse(BaseModel):
    design_prompts: list[str]


class CaptionsResponse(BaseModel):
    captions: list[str]


class DesignImageResponse(BaseModel):
    image_url: str
    prompt_index: int
    remaining_prompts: int


class DesignImageGenerationResponse(BaseModel):
    generation_id: UUID
    image_url: str
    prompt_index: int
    remaining_prompts: int


class DesignImageBatchGenerationResponse(BaseModel):
    generations: list[DesignImageGenerationResponse]


class DesignImageRegenerateRequest(BaseModel):
    feedback: str | None = Field(default=None, max_length=1000)


class DesignImageStatusResponse(BaseModel):
    generation_id: UUID
    image_url: str
    prompt_index: int
    prompt: str
    stored: bool  # False = waiting for user review, True = approved


class DesignImageListResponse(BaseModel):
    total: int
    items: list[DesignImageStatusResponse]
    missing_indexes: list[int]  # designs not generated yet or that failed


class FacebookPostScheduleRequest(BaseModel):
    generation_id: UUID
    schedule_for: datetime | Literal["now"] = "now"
    scheduled_for: datetime | None = None
    live: bool = False


class FacebookPostScheduleResponse(BaseModel):
    schedule_id: UUID
    generation_id: UUID
    image_url: str
    caption: str
    scheduled_for: datetime
    live: bool
    status: str
    facebook_post_id: str | None = None


class PipelineResponse(BaseModel):
    planning: StartPlanningResponse
    design_prompts: DesignPromptsResponse
    captions: CaptionsResponse
    generations: DesignImageBatchGenerationResponse
    stored_images: list[DesignImageResponse]