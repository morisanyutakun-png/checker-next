"""Database engine and session management (SQLAlchemy 2.x async)."""

import ssl

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

# asyncpg does not understand the libpq "sslmode" query-param.
# Strip it from the URL and pass SSL via connect_args instead.
_db_url = settings.DATABASE_URL
_connect_args: dict = {}
if "neon.tech" in _db_url or "sslmode=" in _db_url:
    _ssl_ctx = ssl.create_default_context()
    _ssl_ctx.check_hostname = False
    _ssl_ctx.verify_mode = ssl.CERT_NONE
    _connect_args = {"ssl": _ssl_ctx}
    # Remove sslmode param so asyncpg doesn't choke on it
    import re
    _db_url = re.sub(r"[?&]sslmode=[^&]*", "", _db_url)

engine = create_async_engine(
    _db_url,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    connect_args=_connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:  # type: ignore[misc]
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
