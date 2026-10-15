from fastapi import FastAPI

from src.routes.company_data import company_data_router


app = FastAPI()
app.include_router(company_data_router)

