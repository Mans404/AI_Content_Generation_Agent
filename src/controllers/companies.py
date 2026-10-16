from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from src.agents.company_agent import company_agent
from src.database.companies import async_session_factory
from src.models.companies import CompanyLanguage, CompanyModel, CompanyTone
from src.schemas.company_agent import CompanyContext
from src.schemas.companies import CompanyDataResponse


UPLOAD_DIR = Path("uploads/company_designs")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


async def create_companies(
    company_name: str,
    industry: str,
    reference_design: UploadFile,
    language: CompanyLanguage,
    primary_color: str,
    secondary_color: str,
    tone: CompanyTone,
    audiences: list[str],
    posts_per_week: int,
) -> CompanyDataResponse:

    # 1. Validate filename
    if not reference_design.filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The reference design must have a filename.",
        )

    # 2. Validate content type
    if reference_design.content_type != "image/jpeg":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The reference design must be a JPG image.",
        )

    # 3. Validate file extension
    if not reference_design.filename.lower().endswith((".jpg", ".jpeg")):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The reference design filename must end with .jpg or .jpeg.",
        )

    # 4. Read uploaded image
    image_data = await reference_design.read()

    # 5. Validate JPG signature
    if not image_data.startswith(b"\xff\xd8") or not image_data.endswith(b"\xff\xd9"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The uploaded file is not a valid JPG image.",
        )

    # 6. Generate unique filename
    file_extension = Path(reference_design.filename).suffix.lower()
    stored_filename = f"{uuid4()}{file_extension}"

    # 7. Save image
    file_path = UPLOAD_DIR / stored_filename
    file_path.write_bytes(image_data)

    # 8. Build context for the AI Agent
    company_context = CompanyContext(
        company_id=uuid4(),
        company_name=company_name,
        industry=industry,
        reference_design_path=str(file_path),
    )

    # agent_response = await company_agent.start(company_context) WAIT  %%%%%%%
    
    # New 9. Store the company data in the database

    company = CompanyModel(
        id=company_context.company_id,
        name=company_context.company_name,
        language=language,
        logo_path=company_context.reference_design_path,
        primary_color=primary_color,
        secondary_color=secondary_color,
        tone=tone,
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
        reference_design_filename=stored_filename,
        reference_design_size=len(image_data),
        language=language,
        primary_color=primary_color,
        secondary_color=secondary_color,
        tone=tone,
        audiences=audiences,
        posts_per_week=posts_per_week,
    )