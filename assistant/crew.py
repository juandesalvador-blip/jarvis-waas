"""
crew.py – Lógica del "Asistente General" de Jarvis, construida con CrewAI.

Este módulo define un pequeño equipo (Crew) de agentes que colaboran para
responder preguntas generales del usuario:

    1. Planificador   -> desglosa la solicitud en pasos claros
    2. Investigador    -> reúne los datos/argumentos relevantes
    3. Redactor         -> sintetiza todo en una respuesta final en español

El equipo usa un LLM servido por Ollama (parte de la infraestructura de
Jarvis) a través de LiteLLM, por lo que no depende de ninguna API externa
de pago.

Este módulo es intencionalmente independiente de FastAPI/n8n: expone una
única función pública (`run_assistant`) para que sea fácil de probar con
pytest y de reutilizar desde otros puntos de entrada (CLI, microservicio,
etc.), sin acoplar la lógica de agentes al transporte HTTP.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

from crewai import Agent, Crew, LLM, Process, Task

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")


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
    )


def build_crew(llm: LLM) -> Crew:
    """Define los agentes y tareas del equipo de asistencia general."""
    planner = Agent(
        role="Planificador",
        goal="Desglosar la solicitud del usuario en pasos claros y accionables.",
        backstory=(
            "Eres un analista meticuloso de Jarvis, la plataforma de IA de Ángel. "
            "Tu trabajo es entender qué pide realmente el usuario antes de que "
            "el resto del equipo actúe."
        ),
        llm=llm,
        allow_delegation=False,
        verbose=False,
    )

    researcher = Agent(
        role="Investigador",
        goal="Reunir la información, datos y argumentos necesarios para responder con precisión.",
        backstory=(
            "Eres el investigador de Jarvis. Usas tu conocimiento para reunir "
            "hechos, ejemplos y contexto relevante, siendo honesto cuando algo "
            "es incierto en vez de inventar datos."
        ),
        llm=llm,
        allow_delegation=False,
        verbose=False,
    )

    writer = Agent(
        role="Redactor de Respuestas",
        goal="Sintetizar la investigación en una respuesta clara, breve y útil en español.",
        backstory=(
            "Eres la voz de Jarvis frente al usuario final. Escribes en un "
            "tono amable, profesional y directo, evitando la jerga innecesaria."
        ),
        llm=llm,
        allow_delegation=False,
        verbose=False,
    )

    plan_task = Task(
        description=(
            "El usuario envió este mensaje a Jarvis:\n\n\"{message}\"\n\n"
            "Desglosa en 2 a 4 pasos breves qué información se necesita para "
            "responder bien a este mensaje."
        ),
        expected_output="Una lista corta (2-4 puntos) con el plan de investigación.",
        agent=planner,
    )

    research_task = Task(
        description=(
            "Siguiendo el plan anterior, reúne la información y los "
            "argumentos necesarios para responder a este mensaje del "
            "usuario:\n\n\"{message}\""
        ),
        expected_output="Los hallazgos clave, organizados y listos para redactar la respuesta final.",
        agent=researcher,
        context=[plan_task],
    )

    write_task = Task(
        description=(
            "Con base en los hallazgos anteriores, redacta la respuesta "
            "final en español para el usuario, que responda directamente a "
            "su mensaje:\n\n\"{message}\"\n\n"
            "El tono debe ser amable y profesional. No menciones el proceso "
            "interno del equipo (plan, investigación); entrega solo la "
            "respuesta final como si Jarvis hablara directamente con el usuario."
        ),
        expected_output="La respuesta final, lista para mostrarse al usuario.",
        agent=writer,
        context=[research_task],
    )

    return Crew(
        agents=[planner, researcher, writer],
        tasks=[plan_task, research_task, write_task],
        process=Process.sequential,
        verbose=False,
    )


_crew_singleton: Optional[Crew] = None


def get_crew() -> Crew:
    """Reutiliza la misma instancia del Crew entre peticiones (agentes sin estado)."""
    global _crew_singleton
    if _crew_singleton is None:
        _crew_singleton = build_crew(build_llm())
    return _crew_singleton


def run_assistant(message: str) -> AssistantResult:
    """Punto de entrada público: ejecuta el equipo de agentes sobre `message`."""
    start = time.time()
    try:
        crew = get_crew()
        result = crew.kickoff(inputs={"message": message})
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
