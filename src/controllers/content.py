from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, select

from src.agents.caption_llm import caption_llm
from src.agents.design_prompt_agent import design_prompt_agent
from src.agents.doctor_agent import doctor_agent
from src.controllers.common import build_doctor_context
from src.database.companies import async_session_factory
from src.models.companies import (
    DesignImageModel,
    DesignImageGenerationModel,
    DoctorModel,
    IdeasModel,
    MonthlyIdeasModel,
)
from src.schemas.companies import (
    DesignPromptFeedbackRequest,
    StartPlanningResponse,
)
from src.schemas.doctor_agent import AgentOutput, CaptionOutput, DesignPromptOutput
async def _save_agent_output(
    company_id: UUID,
    agent_output: AgentOutput,
) -> None:
    async with async_session_factory() as session:
        session.add(
            IdeasModel(
                company_id=company_id,
                ideas=agent_output.ideas,
                post_types=agent_output.post_types,
            )
        )
        await session.commit()


async def start_planning(
    owner_id: UUID,
) -> StartPlanningResponse:
    month_start = datetime.now(timezone.utc).replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    async with async_session_factory() as session:
        result = await session.execute(
            select(DoctorModel, MonthlyIdeasModel)
            .join(
                MonthlyIdeasModel,
                MonthlyIdeasModel.company_id == DoctorModel.id,
            )
            .where(
                DoctorModel.owner_id == owner_id,
                MonthlyIdeasModel.month_start == month_start,
            )
        )
        company_and_monthly_ideas = result.one_or_none()

        if company_and_monthly_ideas is None:
            doctor = await session.scalar(
                select(DoctorModel).where(DoctorModel.owner_id == owner_id)
            )
            if doctor is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Create a company profile before starting planning.",
                )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Add monthly ideas before starting planning.",
            )

        doctor, monthly_ideas = company_and_monthly_ideas

    doctor_context = build_doctor_context(doctor, monthly_ideas)
    agent_output = await doctor_agent.start(doctor_context)
    await _save_agent_output(doctor.id, agent_output)

    return StartPlanningResponse(
        month_start=monthly_ideas.month_start,
        doctor_offers=monthly_ideas.doctor_offers,
        advice_and_matters_that_most_people_find_confusing=(
            monthly_ideas.advice_and_matters_that_most_people_find_confusing
        ),
        agent_output=agent_output,
    )


async def start_design_prompt_generation(
    owner_id: UUID,
) -> DesignPromptOutput:
    async with async_session_factory() as session:
        doctor = await session.scalar(
            select(DoctorModel).where(DoctorModel.owner_id == owner_id)
        )
        if doctor is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Create a company profile before generating design prompts.",
            )

        ideas = await session.scalar(
            select(IdeasModel)
            .where(IdeasModel.company_id == doctor.id)
            .order_by(IdeasModel.created_at.desc())
        )
        if ideas is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Generate content ideas before generating design prompts.",
            )

    doctor_context = build_doctor_context(doctor)
    agent_output = AgentOutput.model_validate(
        {
            "ideas": ideas.ideas,
            "post_types": ideas.post_types,
        },
        context={"posts_per_week": doctor.posts_per_week},
    )
    design_prompt_output = await design_prompt_agent.start(
        doctor_context,
        agent_output,
    )

    async with async_session_factory() as session:
        saved_ideas = await session.get(IdeasModel, ideas.id)
        if saved_ideas is None:
            raise RuntimeError(f"Ideas batch {ideas.id} could not be retrieved.")
        await session.execute(
            delete(DesignImageModel).where(DesignImageModel.ideas_id == saved_ideas.id)
        )
        await session.execute(
            delete(DesignImageGenerationModel).where(
                DesignImageGenerationModel.ideas_id == saved_ideas.id
            )
        )
        saved_ideas.design_prompts = design_prompt_output.design_prompts
        await session.commit()

    return design_prompt_output


async def revise_design_prompts(
    owner_id: UUID,
    feedback: DesignPromptFeedbackRequest,
) -> DesignPromptOutput:
    async with async_session_factory() as session:
        doctor = await session.scalar(
            select(DoctorModel).where(DoctorModel.owner_id == owner_id)
        )
        if doctor is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Create a company profile before revising design prompts.",
            )

        ideas = await session.scalar(
            select(IdeasModel)
            .where(IdeasModel.company_id == doctor.id)
            .order_by(IdeasModel.created_at.desc())
        )
        if ideas is None or not ideas.design_prompts:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Generate design prompts before submitting feedback.",
            )

    doctor_context = build_doctor_context(doctor)
    agent_output = AgentOutput.model_validate(
        {
            "ideas": ideas.ideas,
            "post_types": ideas.post_types,
        },
        context={"posts_per_week": doctor.posts_per_week},
    )
    design_prompt_output = await design_prompt_agent.start(
        doctor_context,
        agent_output,
        existing_design_prompts=ideas.design_prompts,
        human_feedback=feedback.feedback,
    )

    async with async_session_factory() as session:
        saved_ideas = await session.get(IdeasModel, ideas.id)
        if saved_ideas is None:
            raise RuntimeError(f"Ideas batch {ideas.id} could not be retrieved.")
        await session.execute(
            delete(DesignImageModel).where(DesignImageModel.ideas_id == saved_ideas.id)
        )
        await session.execute(
            delete(DesignImageGenerationModel).where(
                DesignImageGenerationModel.ideas_id == saved_ideas.id
            )
        )
        saved_ideas.design_prompts = design_prompt_output.design_prompts
        await session.commit()

    return design_prompt_output


async def generate_captions(owner_id: UUID) -> CaptionOutput:
    async with async_session_factory() as session:
        doctor = await session.scalar(
            select(DoctorModel).where(DoctorModel.owner_id == owner_id)
        )
        if doctor is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Create a company profile before generating captions.",
            )

        ideas = await session.scalar(
            select(IdeasModel)
            .where(IdeasModel.company_id == doctor.id)
            .order_by(IdeasModel.created_at.desc())
        )
        if ideas is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Generate content ideas before generating captions.",
            )

    agent_output = AgentOutput.model_validate(
        {
            "ideas": ideas.ideas,
            "post_types": ideas.post_types,
        },
        context={"posts_per_week": doctor.posts_per_week},
    )
    doctor_context = build_doctor_context(doctor)
    caption_output = await caption_llm.start(
        doctor_context,
        agent_output.ideas,
        agent_output.post_types,
    )

    async with async_session_factory() as session:
        saved_ideas = await session.get(IdeasModel, ideas.id)
        if saved_ideas is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The content ideas batch no longer exists.",
            )
        saved_ideas.captions = caption_output.captions
        await session.commit()

    return caption_output
