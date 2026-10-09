from contextlib import asynccontextmanager

from fastapi import FastAPI, Response

from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from app.monitoring import RequestMonitoring, registry

from app.api.chat import router as chat_router
from app.api.profile import router as profile_router
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
app.add_middleware(RequestMonitoring)
app.include_router(profile_router)
app.include_router(chat_router)
app.include_router(faq_router)
app.include_router(reminders_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(generate_latest(registry), headers={"Content-Type": CONTENT_TYPE_LATEST})
