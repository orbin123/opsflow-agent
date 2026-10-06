from fastapi import FastAPI

from app.api.chat import router as chat_router
from app.api.faq import router as faq_router

app = FastAPI(title="OpsFlow Agent")
app.include_router(chat_router)
app.include_router(faq_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
