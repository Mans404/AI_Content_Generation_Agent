import asyncio
import logging
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select

from src.agents.doctor_agent import doctor_agent
from src.database.companies import async_session_factory
from src.models.companies import DoctorLanguage, DoctorModel, DoctorSpecialization
from src.schemas.doctor_agent import DoctorContext
from src.schemas.companies import DoctorDataResponse


logger = logging.getLogger(__name__)

UPLOAD_DIR = Path("uploads/Doctor_designs")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_PICTURE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/jpg"}
ALLOWED_EXTENSIONS = (".jpg", ".jpeg")
JPEG_START = b"\xff\xd8\xff"
JPEG_END = b"\xff\xd9"


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


async def create_companies(
    doctor_name: str,
    doctor_specialization: DoctorSpecialization,
    yourPicture: UploadFile,
    language: DoctorLanguage,
    audiences: list[str],
    types_of_medical_procedures: list[str],
    doctor_offers: list[str],
    advice_and_matters_that_most_people_find_confusing: list[str],
    strengths: list[str],
    posts_per_week: int,
) -> DoctorDataResponse:

    # 1. Validate and read the uploaded image
    image_data = await _read_and_validate_picture(yourPicture)

    # 2. Generate a unique filename (always .jpg since the content is validated JPEG)
    stored_filename = f"{uuid4()}.jpg"
    file_path = UPLOAD_DIR / stored_filename

    # 3. Save image without blocking the event loop
    await asyncio.to_thread(file_path.write_bytes, image_data)

    database_committed = False
    try:
        # 4. Store the doctor data in the database.
        doctor_id = uuid4()
        doctor = DoctorModel(
            id=doctor_id,
            doctor_specialization=doctor_specialization,
            name=doctor_name,
            language=language,
            picture_path=str(file_path),
            audiences=audiences,
            types_of_medical_procedures=types_of_medical_procedures,
            doctor_offers=doctor_offers,
            advice_and_matters_that_most_people_find_confusing=(
                advice_and_matters_that_most_people_find_confusing
            ),
            strengths=strengths,
            posts_per_week=posts_per_week,
        )

        async with async_session_factory() as session:
            session.add(doctor)
            await session.commit()
            database_committed = True

            # Re-read the committed record so the agent always receives the
            # persisted database values.
            saved_doctor = await session.scalar(
                select(DoctorModel).where(DoctorModel.id == doctor_id)
            )
            if saved_doctor is None:
                raise RuntimeError(
                    f"Doctor {doctor_id} was committed but could not be retrieved."
                )

        doctor_context = DoctorContext(
            doctor_id=saved_doctor.id,
            doctor_name=saved_doctor.name,
            doctor_specialization=saved_doctor.doctor_specialization,
            language=saved_doctor.language,
            picture_path=saved_doctor.picture_path,
            audiences=saved_doctor.audiences,
            types_of_medical_procedures=saved_doctor.types_of_medical_procedures,
            doctor_offers=saved_doctor.doctor_offers,
            advice_and_matters_that_most_people_find_confusing=(
                saved_doctor.advice_and_matters_that_most_people_find_confusing
            ),
            strengths=saved_doctor.strengths,
            posts_per_week=saved_doctor.posts_per_week,
        )
        agent_output = await doctor_agent.start(doctor_context)

    except Exception:
        if database_committed:
            logger.exception(
                "Doctor profile was saved, but generating agent output failed."
            )
        else:
            logger.exception(
                "Failed to create doctor profile; removing saved picture."
            )
            file_path.unlink(missing_ok=True)
        raise

    return DoctorDataResponse(
        doctor_name=saved_doctor.name,
        doctor_specialization=saved_doctor.doctor_specialization,
        yourPicture_filename=stored_filename,
        yourPicture_size=len(image_data),
        language=saved_doctor.language,
        audiences=saved_doctor.audiences,
        types_of_medical_procedures=saved_doctor.types_of_medical_procedures,
        doctor_offers=saved_doctor.doctor_offers,
        advice_and_matters_that_most_people_find_confusing=(
            saved_doctor.advice_and_matters_that_most_people_find_confusing
        ),
        strengths=saved_doctor.strengths,
        posts_per_week=saved_doctor.posts_per_week,
        agent_output=agent_output,
    )