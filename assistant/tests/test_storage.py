"""Pruebas de storage.py (memoria de conversación en SQLite)."""

import storage


def test_save_and_get_recent_history(tmp_path):
    db_path = tmp_path / "test.db"

    storage.save_message("user-1", "user", "hola", path=db_path)
    storage.save_message("user-1", "assistant", "¡Hola! ¿En qué te ayudo?", path=db_path)
    storage.save_message("user-1", "user", "¿qué es Jarvis?", path=db_path)

    history = storage.get_recent_history("user-1", path=db_path)

    assert len(history) == 3
    assert history[0] == {"role": "user", "content": "hola"}
    assert history[-1] == {"role": "user", "content": "¿qué es Jarvis?"}


def test_history_is_isolated_per_user(tmp_path):
    db_path = tmp_path / "test.db"

    storage.save_message("user-1", "user", "mensaje de user-1", path=db_path)
    storage.save_message("user-2", "user", "mensaje de user-2", path=db_path)

    history_1 = storage.get_recent_history("user-1", path=db_path)
    history_2 = storage.get_recent_history("user-2", path=db_path)

    assert [m["content"] for m in history_1] == ["mensaje de user-1"]
    assert [m["content"] for m in history_2] == ["mensaje de user-2"]


def test_history_respects_limit(tmp_path):
    db_path = tmp_path / "test.db"

    for i in range(10):
        storage.save_message("user-1", "user", f"mensaje {i}", path=db_path)

    history = storage.get_recent_history("user-1", limit=3, path=db_path)

    assert [m["content"] for m in history] == ["mensaje 7", "mensaje 8", "mensaje 9"]


def test_format_history_for_prompt_empty():
    assert storage.format_history_for_prompt([]) == "(sin conversación previa)"


def test_format_history_for_prompt_with_messages():
    history = [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "¡Hola!"},
    ]
    formatted = storage.format_history_for_prompt(history)
    assert formatted == "Usuario: hola\nJarvis: ¡Hola!"
