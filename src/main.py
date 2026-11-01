from fastapi import FastAPI
from src.routes.companies import companies_router
from src.jwt.auth import router as auth_router

app = FastAPI()
app.include_router(auth_router)
app.include_router(companies_router)
