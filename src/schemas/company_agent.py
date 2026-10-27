from uuid import UUID

from pydantic import BaseModel


class CompanyContext(BaseModel):
    company_id: UUID
    company_name: str
    industry: str
    yourPicture_path: str


class AgentOutput(BaseModel):
    ideas: list[str]
    post_types: list[str]
    company_theme: str