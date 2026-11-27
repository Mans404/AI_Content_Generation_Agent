"""Company route assembly and public router export."""

from fastapi import APIRouter

from src.routes import autopilot, content, images, profile

companies_router = APIRouter(
    prefix="/api/v1/companies",
    tags=["companies"],
)

companies_router.include_router(profile.router)
companies_router.include_router(content.router)
companies_router.include_router(images.router)
companies_router.include_router(autopilot.router)