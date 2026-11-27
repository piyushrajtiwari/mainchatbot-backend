from fastapi import FastAPI
from app.auth.router import router as auth_router
from app.core.middleware import configure_middleware
from app.core.settings import settings
from contextlib import asynccontextmanager
from app.chat.service import init_workflow
from app.chat.router import router as chat_route
from app.db.config import checkpoint_engine

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        async with init_workflow():
            print("Workflow ready - Supabase checkpointer connected")
            yield
    finally:
        await checkpoint_engine.dispose()


app = FastAPI(title="MainChatbot",lifespan=lifespan)
configure_middleware(app, origins=settings.CORS_ORIGINS, frontend_url=settings.FRONTEND_URL)
app.include_router(auth_router)
app.include_router(chat_route)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

