import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Async imports
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker as async_sessionmaker

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/postgres')

# Determine safe sync and async URLs.
# If DATABASE_URL explicitly uses the asyncpg dialect (postgresql+asyncpg://) we must not
# pass that to the synchronous create_engine() — instead convert it to a sync URL.
if DATABASE_URL.startswith('postgresql+asyncpg://'):
    ASYNC_DATABASE_URL = DATABASE_URL
    SYNC_DATABASE_URL = DATABASE_URL.replace('postgresql+asyncpg://', 'postgresql://', 1)
elif DATABASE_URL.startswith('postgresql://'):
    SYNC_DATABASE_URL = DATABASE_URL
    ASYNC_DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+asyncpg://', 1)
else:
    # For other schemes (e.g., sqlite or custom) try to use the same URL for both
    SYNC_DATABASE_URL = DATABASE_URL
    ASYNC_DATABASE_URL = DATABASE_URL

# Synchronous engine & session (used by sync workers / tasks / existing sync code)
engine = create_engine(SYNC_DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Async engine & session (used by FastAPI endpoints when using async DB access)
async_engine = create_async_engine(ASYNC_DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()


async def get_db():
    """Async DB dependency for FastAPI endpoints.

    Yields an AsyncSession and ensures it is closed after the request.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
