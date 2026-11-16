import logging
from pathlib import Path

from src.models.companies import DoctorModel, MonthlyIdeasModel
from src.schemas.doctor_agent import DoctorContext

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path("uploads/Doctor_designs")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
COMPANY_DESIGN_DIR = Path("uploads/company_designs")
COMPANY_DESIGN_DIR.mkdir(parents=True, exist_ok=True)

MAX_PICTURE_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/jpg"}
ALLOWED_EXTENSIONS = (".jpg", ".jpeg")
JPEG_START = b"\xff\xd8\xff"
JPEG_END = b"\xff\xd9"
MAX_MONTHLY_IDEAS = 10


def build_doctor_context(
    doctor: DoctorModel,
    monthly_ideas: MonthlyIdeasModel | None = None,
) -> DoctorContext:
    return DoctorContext(
        doctor_id=doctor.id,
        doctor_name=doctor.name,
        doctor_specialization=doctor.doctor_specialization,
        language=doctor.language,
        picture_path=doctor.picture_path,
        audiences=doctor.audiences,
        types_of_medical_procedures=doctor.types_of_medical_procedures,
        doctor_offers=monthly_ideas.doctor_offers if monthly_ideas is not None else [],
        advice_and_matters_that_most_people_find_confusing=(
            monthly_ideas.advice_and_matters_that_most_people_find_confusing
            if monthly_ideas is not None
            else []
        ),
        strengths=doctor.strengths,
        posts_per_week=doctor.posts_per_week,
    )
