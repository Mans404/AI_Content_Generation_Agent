from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from src.agents.company_agent import company_agent
from src.database.companies import async_session_factory
from src.models.companies import CompanyLanguage, CompanyModel, CompanyIndustry
from src.schemas.company_agent import CompanyContext
from src.schemas.companies import CompanyDataResponse


UPLOAD_DIR = Path("uploads/company_designs")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


async def create_companies(
    company_name: str,
    industry: str,
    yourPicture: UploadFile,
    language: CompanyLanguage,
    audiences: list[str],
    posts_per_week: int,
) -> CompanyDataResponse:

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
    company_context = CompanyContext(
        company_id=uuid4(),
        company_name=company_name,
        industry=industry,
        yourPicture_path=str(file_path),
    )

    # agent_response = await company_agent.start(company_context) WAIT  %%%%%%%
    
    # New 9. Store the company data in the database

    company = CompanyModel(
        id=company_context.company_id,
        industry=industry,
        name=company_context.company_name,
        language=language,
        logo_path=company_context.yourPicture_path,
        audiences=audiences,
        posts_per_week=posts_per_week,
    )

    async with async_session_factory() as session:
        session.add(company)
        await session.commit()

    # end of new 9. Store the company data in the database

    return CompanyDataResponse(
        company_name=company_name,
        industry=industry,
        yourPicture_filename=stored_filename,
        yourPicture_size=len(image_data),
        language=language,
        audiences=audiences,
        posts_per_week=posts_per_week,
    )