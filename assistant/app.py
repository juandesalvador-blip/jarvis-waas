"""
app.py – Microservicio HTTP del "Asistente General" de Jarvis.

Expone el equipo de agentes de CrewAI (definido en `crew.py`) como una API
HTTP sencilla para que n8n (u otro orquestador) pueda invocarlo con un nodo
"HTTP Request", sin necesidad de tener Python/CrewAI instalado dentro del
contenedor de n8n.

Endpoints:
    GET  /health   -> chequeo de salud (usado por jarvis_manager.py)
    POST /assist    -> {"message": str, "user_id": str?, "language": str?}
                       devuelve {"response_text": str, "success": bool, ...}
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from pydantic import BaseModel, Field

from crew import run_assistant
from storage import format_history_for_prompt, get_recent_history, save_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("jarvis.assistant")

app = FastAPI(title="Jarvis General Assistant", version="1.0.0")


class AssistRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Mensaje del usuario a responder.")
    user_id: str | None = Field(default=None, description="Identificador del usuario (opcional).")
    language: str | None = Field(default="es", description="Idioma esperado de la respuesta.")


class AssistResponse(BaseModel):
    response_text: str
    success: bool
    error: str | None = None
    latency_ms: int


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "jarvis-assistant"}


@app.post("/assist", response_model=AssistResponse)
def assist(payload: AssistRequest) -> AssistResponse:
    user_id = payload.user_id or "anonymous"
    logger.info("Nueva solicitud de asistente (user_id=%s)", user_id)

    history = format_history_for_prompt(get_recent_history(user_id))
    result = run_assistant(payload.message, history=history)
    if not result.success:
        logger.error("El agente falló: %s", result.error)

    save_message(user_id, "user", payload.message)
    if result.success:
        save_message(user_id, "assistant", result.response_text)

    return AssistResponse(
        response_text=result.response_text,
        success=result.success,
        error=result.error,
        latency_ms=result.latency_ms,
    )
