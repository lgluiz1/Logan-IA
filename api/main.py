import asyncio
import os
from fastapi import FastAPI
from pydantic import BaseModel

from core.event_bus import EventBus
from core.models.event import LoganEvent
from core.constants import STREAM_COMMANDS

app = FastAPI(title="Logan AI — Gateway API")

# Inicializa o EventBus. No contêiner Docker a URL é redis://redis:6379, no host é localhost
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
event_bus = EventBus(redis_url=REDIS_URL)

@app.on_event("startup")
async def startup_event():
    await event_bus.connect(consumer_name="api_gateway")

@app.on_event("shutdown")
async def shutdown_event():
    await event_bus.disconnect()

class HealthStatus(BaseModel):
    status: str
    version: str

class CommandPayload(BaseModel):
    text: str

@app.get("/health", response_model=HealthStatus)
async def health_check():
    """Endpoint básico para checagem de saúde da API."""
    return {"status": "ok", "version": "1.0.0"}

@app.get("/")
async def root():
    return {"message": "Logan AI API Gateway - Online"}

@app.post("/api/command")
async def inject_command(payload: CommandPayload):
    """Injeta um comando de texto direto no barramento, simulando transcrição."""
    event = LoganEvent(
        event_type="voice.user_input",
        source="api_gateway",
        payload={"text": payload.text},
        priority=60,
    )
    await event_bus.publish(event, stream=STREAM_COMMANDS)
    return {"status": "ok", "message": f"Comando '{payload.text}' enviado com sucesso!"}

@app.post("/api/trigger_wake")
async def trigger_wake():
    """Gatilha manualmente a palavra de ativação 'Logan' (Wake Word)."""
    event = LoganEvent(
        event_type="voice.wake_word",
        source="api_gateway",
        payload={"rms": 0.5},
        priority=100,
    )
    await event_bus.publish(event, stream=STREAM_COMMANDS)
    return {"status": "ok", "message": "Wake Word 'Logan' disparada!"}
