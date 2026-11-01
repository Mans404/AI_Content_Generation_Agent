import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

import jwt
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from src.database.companies import async_session_factory
from src.models.companies import RevokedTokenModel, UserModel
from src.schemas.auth import CreateUserRequest, TokenResponse

load_dotenv()

router = APIRouter(prefix="/auth", tags=["auth"])


def _load_secret_key() -> str:
    key = os.getenv("JWT_SECRET_KEY")
    if not key or len(key) < 32:
        raise RuntimeError(
            "JWT_SECRET_KEY must be configured with at least 32 characters."
        )
    return key


SECRET_KEY = _load_secret_key()
ALGORITHM = "HS256"
JWT_ISSUER = os.getenv("JWT_ISSUER", "content-generation-api")
ACCESS_TOKEN_EXPIRE_MINUTES = 30
password_hash = PasswordHash.recommended()
oauth2_bearer = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_db():
    async with async_session_factory() as session:
        yield session


db_dependency = Annotated[AsyncSession, Depends(get_db)]


def create_access_token(data: dict[str, Any]) -> str:
    claims = {**data}
    claims.update(
        {
            "exp": datetime.now(timezone.utc)
            + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
            "iss": JWT_ISSUER,
            "jti": os.urandom(16).hex(),
            "type": "access",
        }
    )
    return jwt.encode(claims, SECRET_KEY, algorithm=ALGORITHM)


async def get_token_payload(
    token: Annotated[str, Depends(oauth2_bearer)],
    db: db_dependency,
) -> dict[str, Any]:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            issuer=JWT_ISSUER,
            options={"require": ["exp", "iss", "jti", "sub", "type"]},
        )
        if payload.get("type") != "access":
            raise credentials_exception
        username = payload.get("sub")
        jti = payload.get("jti")
        if not isinstance(username, str) or not username:
            raise credentials_exception
        if not isinstance(jti, str) or not jti:
            raise credentials_exception
    except jwt.InvalidTokenError:
        raise credentials_exception from None

    revoked = await db.scalar(
        select(RevokedTokenModel).where(RevokedTokenModel.jti == jti)
    )
    if revoked is not None:
        raise credentials_exception
    return payload


async def get_current_user(
    payload: Annotated[dict[str, Any], Depends(get_token_payload)],
    db: db_dependency,
) -> UserModel:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user = await db.scalar(
        select(UserModel).where(UserModel.user_name == payload["sub"])
    )
    if user is None:
        raise credentials_exception
    return user


CurrentUser = Annotated[UserModel, Depends(get_current_user)]


@router.post("/register", response_model=TokenResponse)
async def register_user(request: CreateUserRequest, db: db_dependency):
    new_user = UserModel(
        user_name=request.username,
        password=password_hash.hash(request.password),
    )
    db.add(new_user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username is already registered.",
        ) from None

    return TokenResponse(
        access_token=create_access_token({"sub": new_user.user_name}),
        token_type="bearer",
    )


@router.post("/login", response_model=TokenResponse)
async def login_user(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: db_dependency,
):
    user = await db.scalar(
        select(UserModel).where(UserModel.user_name == form_data.username)
    )
    if user is None or not password_hash.verify(form_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenResponse(
        access_token=create_access_token({"sub": user.user_name}),
        token_type="bearer",
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_user(
    payload: Annotated[dict[str, Any], Depends(get_token_payload)],
    current_user: CurrentUser,
    db: db_dependency,
) -> None:
    db.add(
        RevokedTokenModel(
            jti=payload["jti"],
            user_id=current_user.id,
            expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
        )
    )
    await db.commit()
