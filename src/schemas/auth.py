from pydantic import BaseModel, Field


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=12, max_length=128)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str