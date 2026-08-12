"""
Pruebas unitarias de `crew.run_assistant`.

No se conecta a Ollama de verdad: se sustituye `Crew.kickoff` por un doble
de prueba, para que las pruebas sean rápidas, deterministas y puedan
correr en CI sin la infraestructura completa de Jarvis levantada.
"""

from unittest.mock import patch

import crew


class FakeCrewOutput:
    """Imita el objeto CrewOutput que devuelve crewai al terminar el kickoff."""

    def __init__(self, text: str):
        self._text = text

    def __str__(self) -> str:
        return self._text


def test_run_assistant_success():
    crew._crew_singleton = None  # aislar el test de ejecuciones previas

    with patch.object(crew, "get_crew") as mock_get_crew:
        mock_crew = mock_get_crew.return_value
        mock_crew.kickoff.return_value = FakeCrewOutput("Respuesta de prueba de Jarvis.")

        result = crew.run_assistant("¿Qué es Jarvis?")

    assert result.success is True
    assert result.response_text == "Respuesta de prueba de Jarvis."
    assert result.error is None
    assert result.latency_ms >= 0
    mock_crew.kickoff.assert_called_once_with(
        inputs={"message": "¿Qué es Jarvis?", "history": "(sin conversación previa)"}
    )


def test_run_assistant_handles_failure():
    crew._crew_singleton = None

    with patch.object(crew, "get_crew") as mock_get_crew:
        mock_crew = mock_get_crew.return_value
        mock_crew.kickoff.side_effect = RuntimeError("Ollama no disponible")

        result = crew.run_assistant("hola")

    assert result.success is False
    assert result.error == "Ollama no disponible"
    assert "problema" in result.response_text.lower()


def test_get_crew_is_cached_singleton():
    crew._crew_singleton = None

    with patch.object(crew, "build_crew") as mock_build_crew, patch.object(
        crew, "build_llm"
    ) as mock_build_llm:
        mock_build_crew.return_value = "crew-instance"

        first = crew.get_crew()
        second = crew.get_crew()

    assert first is second
    mock_build_crew.assert_called_once()
    mock_build_llm.assert_called_once()
