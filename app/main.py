from fastapi import FastAPI

from app.api.faq import router as faq_router

app = FastAPI(title="OpsFlow Agent")
app.include_router(faq_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
