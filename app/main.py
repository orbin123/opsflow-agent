from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.chat import router as chat_router
from app.api.faq import router as faq_router
from app.api.reminders import router as reminders_router
from app.sessions import close_chat_store
from app.chat_stream import drain_stream_workers


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        await drain_stream_workers()
        close_chat_store()


app = FastAPI(title="OpsFlow Agent", lifespan=lifespan)
app.include_router(chat_router)
app.include_router(faq_router)
app.include_router(reminders_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
