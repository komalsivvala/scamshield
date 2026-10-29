import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import FileResponse, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from . import pipeline  # noqa: E402
from .llm import TokenFactory  # noqa: E402
from .search import Tavily  # noqa: E402

log = logging.getLogger("scamshield")
STATIC = Path(__file__).parent / "static"
MOCK = os.getenv("MOCK_MODE", "0") == "1"

llm = TokenFactory()
tavily = Tavily()


@asynccontextmanager
async def lifespan(_app):
    if llm.configured:
        try:
            models = await llm.resolve_models()
            log.warning("Nemotron models resolved: %s", models)
        except Exception as ex:  # surfaced via /api/health
            log.error("Could not list Token Factory models: %s", ex)
    yield


app = FastAPI(title="ScamShield", lifespan=lifespan)


class AnalyzeRequest(BaseModel):
    text: str = Field("", max_length=8000)
    image: str | None = Field(None, description="data: URL of a screenshot")
    language: str = "English"
    region: str = "India"


@app.get("/api/health")
async def health():
    return {
        "mock": MOCK,
        "nebius": llm.configured,
        "tavily": tavily.configured,
        "models": llm.models,
    }


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    image = req.image if req.image and req.image.startswith("data:image/") and len(req.image) < 8_000_000 else None

    async def stream():
        try:
            async for ev in pipeline.run(req.text, image, req.language, req.region, llm, tavily, mock=MOCK or not llm.configured):
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as ex:
            log.exception("analysis failed")
            yield f"data: {json.dumps({'type': 'error', 'message': str(ex)[:300]})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
