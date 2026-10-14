import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from agents import create_agents
from config import Settings
from orchestration.graph import build_graph
from voice import VoiceGateway

from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    agents = create_agents(settings)
    voice = VoiceGateway(settings)

    try:
        await asyncio.gather(*(agent.start() for agent in agents.values()))
        app.state.graph = build_graph(agents)
        app.state.voice = voice
        yield
    finally:
        await asyncio.gather(
            voice.close(),
            *(agent.close() for agent in agents.values()),
            return_exceptions=True,
        )


app = FastAPI(lifespan=lifespan)
app.include_router(router)
