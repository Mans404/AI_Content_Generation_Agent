from fastapi import FastAPI

from src.routes.companies import companies_router


app = FastAPI()
app.include_router(companies_router)
