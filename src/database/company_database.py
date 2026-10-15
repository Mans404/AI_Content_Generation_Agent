###############################
from configparser import RawConfigParser
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


alembic_config = RawConfigParser()
alembic_config.read(
    Path(__file__).resolve().parents[1] / "models" / "alembic.ini"
)
database_url = alembic_config.get("alembic", "sqlalchemy.url", fallback="")
if not database_url:
    raise RuntimeError("DATABASE_URL must be configured.")

if database_url.startswith("postgresql://"):
    database_url = database_url.replace(
        "postgresql://",
        "postgresql+psycopg://",
        1,
    )

engine = create_async_engine(database_url)
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
###############################