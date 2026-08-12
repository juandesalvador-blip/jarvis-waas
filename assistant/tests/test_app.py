"""Pruebas del microservicio HTTP (`app.py`), sin llamar a Ollama ni a SQLite real."""

from unittest.mock import patch

from fastapi.testclient import TestClient

import app as app_module
from crew import AssistantResult


client = TestClient(app_module.app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "jarvis-assistant"}


def test_assist_endpoint_success():
    fake_result = AssistantResult(
        response_text="Hola, soy Jarvis.",
        success=True,
        error=None,
        latency_ms=123,
    )
    with patch.object(app_module, "run_assistant", return_value=fake_result) as mock_run, \
         patch.object(app_module, "get_recent_history", return_value=[]), \
         patch.object(app_module, "save_message") as mock_save:
        response = client.post(
            "/assist", json={"message": "hola", "user_id": "juan", "language": "es"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["response_text"] == "Hola, soy Jarvis."
    assert body["success"] is True
    assert body["latency_ms"] == 123

    mock_run.assert_called_once_with("hola", history="(sin conversación previa)")
    assert mock_save.call_count == 2  # guarda el mensaje del usuario y la respuesta


def test_assist_endpoint_requires_message():
    response = client.post("/assist", json={"message": ""})
    assert response.status_code == 422


def test_assist_endpoint_propagates_failure_flag():
    fake_result = AssistantResult(
        response_text="Lo siento, tuve un problema...",
        success=False,
        error="timeout",
        latency_ms=50,
    )
    with patch.object(app_module, "run_assistant", return_value=fake_result), \
         patch.object(app_module, "get_recent_history", return_value=[]), \
         patch.object(app_module, "save_message") as mock_save:
        response = client.post("/assist", json={"message": "hola"})

    body = response.json()
    assert body["success"] is False
    assert body["error"] == "timeout"
    # Solo se guarda el mensaje del usuario; no una respuesta fallida.
    assert mock_save.call_count == 1


def test_assist_endpoint_uses_default_user_id_when_missing():
    fake_result = AssistantResult(response_text="ok", success=True, latency_ms=1)
    with patch.object(app_module, "run_assistant", return_value=fake_result), \
         patch.object(app_module, "get_recent_history", return_value=[]) as mock_history, \
         patch.object(app_module, "save_message") as mock_save:
        client.post("/assist", json={"message": "hola"})

    mock_history.assert_called_once_with("anonymous")
    mock_save.assert_any_call("anonymous", "user", "hola")
