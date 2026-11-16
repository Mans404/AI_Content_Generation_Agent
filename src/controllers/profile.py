import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select

from src.controllers.common import (
    ALLOWED_CONTENT_TYPES,
    ALLOWED_EXTENSIONS,
    JPEG_END,
    JPEG_START,
    MAX_MONTHLY_IDEAS,
    MAX_PICTURE_SIZE_BYTES,
)
from src.database.companies import async_session_factory
from src.models.companies import (
    DoctorLanguage,
    DoctorModel,
    DoctorSpecialization,
    MonthlyIdeasModel,
)
from src.schemas.companies import DoctorDataResponse, MonthlyIdeasResponse
from src.services.storage import (
    DOCTOR_IMAGES_BUCKET,
    filename_from_path,
    storage_path_from_url,
    supabase_storage,
)

logger = logging.getLogger(__name__)

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

    storage_path: str | None = None
    storage_url: str | None = None
    old_picture_path: str | None = None
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

            # All request checks passed; only now upload the new object.
            if image_data is not None:
                storage_path = f"{uuid4()}.jpg"
                storage_url = await supabase_storage.upload(
                    DOCTOR_IMAGES_BUCKET,
                    storage_path,
                    image_data,
                    "image/jpeg",
                )

            if doctor is None:
                if storage_url is None:
                    raise RuntimeError("The doctor picture upload did not return a URL.")
                doctor = DoctorModel(
                    id=uuid4(),
                    owner_id=owner_id,
                    picture_path=storage_url,
                )
                session.add(doctor)
            elif storage_url is not None:
                old_picture_path = doctor.picture_path
                doctor.picture_path = storage_url

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

        # Remove the replaced object. A failure here must not fail the request.
        if old_picture_path is not None:
            old_storage_path = storage_path_from_url(
                old_picture_path, DOCTOR_IMAGES_BUCKET
            )
            if old_storage_path is not None:
                try:
                    await supabase_storage.delete(
                        DOCTOR_IMAGES_BUCKET, old_storage_path
                    )
                except Exception:
                    logger.warning(
                        "Could not delete old doctor picture %s",
                        old_picture_path,
                        exc_info=True,
                    )

    except HTTPException:
        # Client errors: no stack trace in the logs. Clean up any new object.
        if not database_committed and storage_path is not None:
            try:
                await supabase_storage.delete(DOCTOR_IMAGES_BUCKET, storage_path)
            except Exception:
                logger.warning(
                    "Could not remove the uncommitted doctor picture %s",
                    storage_path,
                    exc_info=True,
                )
        raise

    except Exception:
        if database_committed:
            logger.exception(
                "Doctor profile was saved, but generating or saving agent output failed."
            )
        else:
            logger.exception("Failed to save doctor profile; removing new picture.")
            if storage_path is not None:
                try:
                    await supabase_storage.delete(DOCTOR_IMAGES_BUCKET, storage_path)
                except Exception:
                    logger.warning(
                        "Could not remove the uncommitted doctor picture %s",
                        storage_path,
                        exc_info=True,
                    )
        raise

    saved_picture_path = saved_doctor.picture_path
    saved_picture_storage_path = storage_path_from_url(
        saved_picture_path, DOCTOR_IMAGES_BUCKET
    )
    if image_data is not None:
        picture_size = len(image_data)
    elif saved_picture_storage_path is not None:
        picture_size = await supabase_storage.size(
            DOCTOR_IMAGES_BUCKET, saved_picture_storage_path
        )
    else:
        picture_size = Path(saved_picture_path).stat().st_size

    return (
        DoctorDataResponse(
            doctor_name=saved_doctor.name,
            doctor_specialization=saved_doctor.doctor_specialization,
            yourPicture_filename=filename_from_path(saved_picture_path),
            yourPicture_size=picture_size,
            language=saved_doctor.language,
            audiences=saved_doctor.audiences,
            types_of_medical_procedures=saved_doctor.types_of_medical_procedures,
            strengths=saved_doctor.strengths,
            posts_per_week=saved_doctor.posts_per_week,
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
