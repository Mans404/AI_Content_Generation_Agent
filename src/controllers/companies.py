import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select

from src.agents.doctor_agent import doctor_agent
from src.database.companies import async_session_factory
from src.models.companies import (
    DoctorLanguage,
    DoctorModel,
    DoctorSpecialization,
    IdeasModel,
    MonthlyIdeasModel,
)
from src.schemas.doctor_agent import AgentOutput, DoctorContext
from src.schemas.companies import (
    DoctorDataResponse,
    MonthlyIdeasResponse,
    StartPlanningResponse,
)


logger = logging.getLogger(__name__)

UPLOAD_DIR = Path("uploads/Doctor_designs")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_PICTURE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/jpg"}
ALLOWED_EXTENSIONS = (".jpg", ".jpeg")
JPEG_START = b"\xff\xd8\xff"
JPEG_END = b"\xff\xd9"
MAX_MONTHLY_IDEAS = 10


async def _save_agent_output(company_id: UUID, agent_output: AgentOutput) -> None:
    async with async_session_factory() as session:
        session.add(
            IdeasModel(
                company_id=company_id,
                ideas=agent_output.ideas,
                post_types=agent_output.post_types,
            )
        )
        await session.commit()


async def _read_and_validate_picture(picture: UploadFile) -> bytes:
    # 1. Filename
    if not picture.filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The profile picture must have a filename.",
        )

    # 2. Content type
    if picture.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The profile picture must be a JPG image.",
        )

    # 3. Extension
    if not picture.filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The profile picture filename must end with .jpg or .jpeg.",
        )

    # 4. Read with a hard size cap (never load an unbounded upload into memory)
    try:
        image_data = await picture.read(MAX_PICTURE_SIZE_BYTES + 1)
    finally:
        await picture.close()

    # 5. Empty / too large
    if not image_data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The uploaded profile picture is empty.",
        )

    if len(image_data) > MAX_PICTURE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                "The profile picture must not exceed "
                f"{MAX_PICTURE_SIZE_BYTES // (1024 * 1024)} MB."
            ),
        )

    # 6. JPEG signature (start marker + end marker, ignoring trailing zero padding)
    if not image_data.startswith(JPEG_START) or not image_data.rstrip(b"\x00").endswith(
        JPEG_END
    ):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The uploaded file is not a valid JPG image.",
        )

    return image_data


async def create_or_update_company(
    owner_id: UUID,
    doctor_name: str,
    doctor_specialization: DoctorSpecialization,
    yourPicture: UploadFile | None,
    language: DoctorLanguage,
    audiences: list[str],
    types_of_medical_procedures: list[str],
    strengths: list[str],
    posts_per_week: int,
) -> tuple[DoctorDataResponse, bool]:
    # Validate the upload first: it needs no DB access, so bad files fail fast.
    image_data: bytes | None = None
    if yourPicture is not None:
        image_data = await _read_and_validate_picture(yourPicture)

    file_path: Path | None = None
    old_file_path: Path | None = None
    database_committed = False

    try:
        async with async_session_factory() as session:
            doctor = await session.scalar(
                select(DoctorModel)
                .where(DoctorModel.owner_id == owner_id)
                .with_for_update()
            )
            created = doctor is None

            # Fail fast: creating a profile requires a picture. Checked before
            # anything is written to disk.
            if created and image_data is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="The profile picture is required when creating a profile.",
                )

            # All request checks passed; only now touch the filesystem.
            if image_data is not None:
                file_path = UPLOAD_DIR / f"{uuid4()}.jpg"
                await asyncio.to_thread(file_path.write_bytes, image_data)

            if doctor is None:
                doctor = DoctorModel(
                    id=uuid4(),
                    owner_id=owner_id,
                    picture_path=str(file_path),
                )
                session.add(doctor)
            elif file_path is not None:
                old_file_path = Path(doctor.picture_path)
                doctor.picture_path = str(file_path)

            doctor.doctor_specialization = doctor_specialization
            doctor.name = doctor_name
            doctor.language = language
            doctor.audiences = audiences
            doctor.types_of_medical_procedures = types_of_medical_procedures
            month_start = datetime.now(timezone.utc).replace(
                day=1,
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            monthly_ideas = await session.scalar(
                select(MonthlyIdeasModel)
                .where(
                    MonthlyIdeasModel.company_id == doctor.id,
                    MonthlyIdeasModel.month_start == month_start,
                )
            )
            doctor.strengths = strengths
            doctor.posts_per_week = posts_per_week

            await session.commit()
            database_committed = True

            saved_doctor = await session.scalar(
                select(DoctorModel).where(DoctorModel.id == doctor.id)
            )
            if saved_doctor is None:
                raise RuntimeError(
                    f"Doctor {doctor.id} was committed but could not be retrieved."
                )

        # Remove the replaced picture. A failure here must not fail the request.
        if old_file_path is not None and old_file_path != file_path:
            try:
                old_file_path.unlink(missing_ok=True)
            except OSError:
                logger.warning(
                    "Could not delete old picture %s", old_file_path, exc_info=True
                )

        doctor_context = DoctorContext(
            doctor_id=saved_doctor.id,
            doctor_name=saved_doctor.name,
            doctor_specialization=saved_doctor.doctor_specialization,
            language=saved_doctor.language,
            picture_path=saved_doctor.picture_path,
            audiences=saved_doctor.audiences,
            types_of_medical_procedures=saved_doctor.types_of_medical_procedures,
            doctor_offers=(
                monthly_ideas.doctor_offers if monthly_ideas is not None else []
            ),
            advice_and_matters_that_most_people_find_confusing=(
                monthly_ideas.advice_and_matters_that_most_people_find_confusing
                if monthly_ideas is not None
                else []
            ),
            strengths=saved_doctor.strengths,
            posts_per_week=saved_doctor.posts_per_week,
        )
        agent_output = await doctor_agent.start(doctor_context)
        await _save_agent_output(saved_doctor.id, agent_output)

    except HTTPException:
        # Client errors: no stack trace in the logs. Clean up any new file.
        if not database_committed and file_path is not None:
            file_path.unlink(missing_ok=True)
        raise

    except Exception:
        if database_committed:
            logger.exception(
                "Doctor profile was saved, but generating or saving agent output failed."
            )
        else:
            logger.exception("Failed to save doctor profile; removing new picture.")
            if file_path is not None:
                file_path.unlink(missing_ok=True)
        raise

    return (
        DoctorDataResponse(
            doctor_name=saved_doctor.name,
            doctor_specialization=saved_doctor.doctor_specialization,
            yourPicture_filename=Path(saved_doctor.picture_path).name,
            yourPicture_size=(
                len(image_data)
                if image_data is not None
                else Path(saved_doctor.picture_path).stat().st_size
            ),
            language=saved_doctor.language,
            audiences=saved_doctor.audiences,
            types_of_medical_procedures=saved_doctor.types_of_medical_procedures,
            strengths=saved_doctor.strengths,
            posts_per_week=saved_doctor.posts_per_week,
            agent_output=agent_output,
        ),
        created,
    )


async def create_or_update_monthly_ideas(
    owner_id: UUID,
    doctor_offers: list[str],
    advice_and_matters_that_most_people_find_confusing: list[str],
) -> MonthlyIdeasResponse:
    if (
        len(doctor_offers) > MAX_MONTHLY_IDEAS
        or len(advice_and_matters_that_most_people_find_confusing)
        > MAX_MONTHLY_IDEAS
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Doctor offers and confusing matters are limited to "
                f"{MAX_MONTHLY_IDEAS} items per month."
            ),
        )

    month_start = datetime.now(timezone.utc).replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    async with async_session_factory() as session:
        doctor = await session.scalar(
            select(DoctorModel)
            .where(DoctorModel.owner_id == owner_id)
            .with_for_update()
        )
        if doctor is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Create a company profile before adding monthly ideas.",
            )

        monthly_ideas = await session.scalar(
            select(MonthlyIdeasModel)
            .where(
                MonthlyIdeasModel.company_id == doctor.id,
                MonthlyIdeasModel.month_start == month_start,
            )
            .with_for_update()
        )
        if monthly_ideas is None:
            monthly_ideas = MonthlyIdeasModel(
                company_id=doctor.id,
                month_start=month_start,
            )
            session.add(monthly_ideas)

        monthly_ideas.doctor_offers = doctor_offers
        monthly_ideas.advice_and_matters_that_most_people_find_confusing = (
            advice_and_matters_that_most_people_find_confusing
        )
        await session.commit()

    return MonthlyIdeasResponse(
        month_start=month_start,
        doctor_offers=doctor_offers,
        advice_and_matters_that_most_people_find_confusing=(
            advice_and_matters_that_most_people_find_confusing
        ),
    )


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

    doctor_context = DoctorContext(
        doctor_id=doctor.id,
        doctor_name=doctor.name,
        doctor_specialization=doctor.doctor_specialization,
        language=doctor.language,
        picture_path=doctor.picture_path,
        audiences=doctor.audiences,
        types_of_medical_procedures=doctor.types_of_medical_procedures,
        doctor_offers=monthly_ideas.doctor_offers,
        advice_and_matters_that_most_people_find_confusing=(
            monthly_ideas.advice_and_matters_that_most_people_find_confusing
        ),
        strengths=doctor.strengths,
        posts_per_week=doctor.posts_per_week,
    )
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