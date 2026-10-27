from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from src.agents.doctor_agent import doctor_agent
from src.database.companies import async_session_factory
from src.models.companies import DoctorLanguage, DoctorModel, DoctorSpecialization
from src.schemas.doctor_agent import DoctorContext
from src.schemas.companies import DoctorDataResponse


UPLOAD_DIR = Path("uploads/Doctor_designs")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


async def create_companies(
    doctor_name: str,
    doctor_specialization: str,
    yourPicture: UploadFile,
    language: DoctorLanguage,
    audiences: list[str],
    posts_per_week: int,
) -> DoctorDataResponse:

    # 1. Validate filename
    if not yourPicture.filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The reference design must have a filename.",
        )

    # 2. Validate content type
    if yourPicture.content_type != "image/jpeg":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The reference design must be a JPG image.",
        )

    # 3. Validate file extension
    if not yourPicture.filename.lower().endswith((".jpg", ".jpeg")):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The reference design filename must end with .jpg or .jpeg.",
        )

    # 4. Read uploaded image
    image_data = await yourPicture.read()

    # 5. Validate JPG signature
    if not image_data.startswith(b"\xff\xd8") or not image_data.endswith(b"\xff\xd9"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The uploaded file is not a valid JPG image.",
        )

    # 6. Generate unique filename
    file_extension = Path(yourPicture.filename).suffix.lower()
    stored_filename = f"{uuid4()}{file_extension}"

    # 7. Save image
    file_path = UPLOAD_DIR / stored_filename
    file_path.write_bytes(image_data)

    # 8. Build context for the AI Agent
    Doctor_context = DoctorContext(
        doctor_id=uuid4(),
        doctor_name=doctor_name,
        doctor_specialization=doctor_specialization,
        picture_path=str(file_path),
    )

    # agent_response = await doctor_agent.start(Doctor_context) WAIT  %%%%%%%
    
    # New 9. Store the Doctor data in the database

    Doctor = DoctorModel(
        id=Doctor_context.doctor_id,
        doctor_specialization=doctor_specialization,
        name=Doctor_context.doctor_name,
        language=language,
        picture_path=Doctor_context.picture_path,
        audiences=audiences,
        posts_per_week=posts_per_week,
    )

    async with async_session_factory() as session:
        session.add(Doctor)
        await session.commit()

    # end of new 9. Store the Doctor data in the database

    return DoctorDataResponse(
        doctor_name=doctor_name,
        doctor_specialization=doctor_specialization,
        yourPicture_filename=stored_filename,
        yourPicture_size=len(image_data),
        language=language,
        audiences=audiences,
        posts_per_week=posts_per_week,
    )