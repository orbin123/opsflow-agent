from fastapi import FastAPI

app = FastAPI(title="OpsFlow Agent")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
