"""Pruebas del microservicio HTTP (`app.py`), sin llamar a Ollama de verdad."""

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
    with patch.object(app_module, "run_assistant", return_value=fake_result):
        response = client.post(
            "/assist", json={"message": "hola", "user_id": "juan", "language": "es"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["response_text"] == "Hola, soy Jarvis."
    assert body["success"] is True
    assert body["latency_ms"] == 123


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
    with patch.object(app_module, "run_assistant", return_value=fake_result):
        response = client.post("/assist", json={"message": "hola"})

    body = response.json()
    assert body["success"] is False
    assert body["error"] == "timeout"
