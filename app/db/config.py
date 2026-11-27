from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession, AsyncAttrs
from sqlalchemy.orm import DeclarativeBase
from fastapi import Depends
from typing import Annotated
from app.core.settings import settings
from sqlalchemy.engine import make_url

DATABASE_URL = settings.DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=True,connect_args={"statement_cache_size": 0},)
checkpoint_engine = create_async_engine(
    make_url(settings.CHECKPOINT_DATABASE_URL).set(drivername="postgresql+psycopg"),
    connect_args={"prepare_threshold": None},
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False) 

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session 
        
SessionDB = Annotated[AsyncSession,Depends(get_db)]
