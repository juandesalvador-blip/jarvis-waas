"""
crew.py – Lógica del "Asistente General" de Jarvis, construida con CrewAI.

Núcleo compacto: **un solo agente** responde directamente al usuario,
usando el historial reciente de la conversación como contexto. Esto es
deliberadamente más simple (y ~3x más rápido) que un equipo de varios
agentes secuenciales; si en el futuro una tarea concreta lo justifica
(por ejemplo, investigación multi-paso), se puede volver a un Crew de
varios agentes sin cambiar la interfaz pública de este módulo.

El agente usa un LLM servido por Ollama (parte de la infraestructura de
Jarvis) a través de LiteLLM, por lo que no depende de ninguna API externa
de pago.

Este módulo es intencionalmente independiente de FastAPI: expone una
única función pública (`run_assistant`) para que sea fácil de probar con
pytest y de reutilizar desde otros puntos de entrada, sin acoplar la
lógica del agente al transporte HTTP ni al almacenamiento.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

from crewai import Agent, Crew, LLM, Process, Task

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
# Ollama en CPU (sin GPU) puede tardar bastante por llamada; el timeout por
# defecto de LiteLLM (600s) es insuficiente en hardware modesto.
LLM_TIMEOUT_SECONDS = int(os.environ.get("LLM_TIMEOUT_SECONDS", "1800"))

# Evita que CrewAI muestre prompts interactivos (confirmación de telemetría,
# "¿ver tus trazas de ejecución?") en un servicio no interactivo como este.
os.environ.setdefault("CREWAI_TESTING", "true")


@dataclass
class AssistantResult:
    response_text: str
    success: bool
    error: Optional[str] = None
    latency_ms: int = 0


def build_llm() -> LLM:
    """Crea el cliente LLM apuntando al Ollama de la infraestructura Jarvis."""
    return LLM(
        model=f"ollama/{OLLAMA_MODEL}",
        base_url=OLLAMA_BASE_URL,
        api_base=OLLAMA_BASE_URL,
        temperature=0.4,
        timeout=LLM_TIMEOUT_SECONDS,
    )


def build_crew(llm: LLM) -> Crew:
    """Define el agente único y su tarea para el asistente general."""
    assistant = Agent(
        role="Asistente General de Jarvis",
        goal="Responder directamente y con precisión a las preguntas del usuario, en español.",
        backstory=(
            "Eres Jarvis, un asistente de IA amable, directo y profesional. "
            "Respondes de forma clara y concisa, usando el historial de la "
            "conversación cuando sea relevante, y siendo honesto cuando no "
            "sabes algo en vez de inventar datos."
        ),
        llm=llm,
        allow_delegation=False,
        verbose=False,
    )

    respond_task = Task(
        description=(
            "Historial reciente de la conversación con este usuario:\n"
            "{history}\n\n"
            "Nuevo mensaje del usuario:\n\"{message}\"\n\n"
            "Responde directamente al usuario en español, de forma clara, "
            "breve y útil, teniendo en cuenta el historial si aplica. No "
            "menciones que eres un 'agente' ni describas tu proceso interno; "
            "responde como si estuvieras hablando directamente con la persona."
        ),
        expected_output="La respuesta final, lista para mostrarse al usuario.",
        agent=assistant,
    )

    return Crew(
        agents=[assistant],
        tasks=[respond_task],
        process=Process.sequential,
        verbose=False,
    )


_crew_singleton: Optional[Crew] = None


def get_crew() -> Crew:
    """Reutiliza la misma instancia del Crew entre peticiones (agente sin estado propio)."""
    global _crew_singleton
    if _crew_singleton is None:
        _crew_singleton = build_crew(build_llm())
    return _crew_singleton


def run_assistant(message: str, history: str = "(sin conversación previa)") -> AssistantResult:
    """Punto de entrada público: ejecuta el agente sobre `message` con `history` como contexto."""
    start = time.time()
    try:
        crew = get_crew()
        result = crew.kickoff(inputs={"message": message, "history": history})
        return AssistantResult(
            response_text=str(result).strip(),
            success=True,
            latency_ms=int((time.time() - start) * 1000),
        )
    except Exception as exc:  # noqa: BLE001 - queremos capturar cualquier fallo del LLM/red
        return AssistantResult(
            response_text="Lo siento, tuve un problema para procesar tu mensaje. Intenta de nuevo en un momento.",
            success=False,
            error=str(exc),
            latency_ms=int((time.time() - start) * 1000),
        )
