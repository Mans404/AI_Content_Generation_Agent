from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from src.routes.companies import companies_router
from src.jwt.auth import router as auth_router

app = FastAPI()
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.include_router(auth_router)
app.include_router(companies_router)
