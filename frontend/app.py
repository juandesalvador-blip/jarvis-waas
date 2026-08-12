"""
Jarvis – Frontend de chat (Streamlit)

Interfaz de chat que habla directamente con el microservicio del
Asistente General (CrewAI + Ollama). En el núcleo compacto no hay
intermediario (n8n): si más adelante se agrega n8n (profile "extras")
para integraciones multi-canal, basta con apuntar ASSISTANT_URL a su
webhook en vez de al asistente. El soporte de voz (STT/TTS) real
depende de las capacidades del navegador (Web Speech API) y de las
librerías locales (pyttsx3); aquí se deja el punto de integración
documentado en `speak()` y en el widget de audio.
"""

import os
import uuid

import requests
import streamlit as st

ASSISTANT_URL = os.environ.get(
    "ASSISTANT_URL", "http://jarvis-assistant:8000/assist"
)
# Ollama en CPU puede tardar bastante en responder; dejamos margen amplio.
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("REQUEST_TIMEOUT_SECONDS", "600"))

st.set_page_config(page_title="Jarvis – AI Workforce", page_icon="🤖", layout="centered")
st.title("🤖 Jarvis – AI Workforce as a Service")
st.caption("Núcleo compacto · Asistente General (CrewAI + Ollama)")

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []


def send_to_assistant(text: str) -> str:
    """Envía el mensaje al Asistente General y devuelve su respuesta."""
    payload = {
        "user_id": st.session_state.session_id,
        "message": text,
        "language": "es",
    }
    try:
        resp = requests.post(ASSISTANT_URL, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        return data.get("response_text", "(sin respuesta del asistente)")
    except requests.exceptions.RequestException as exc:
        return f"⚠️ No se pudo contactar al asistente: {exc}"


for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

prompt = st.chat_input("Escribe tu mensaje...")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Jarvis está pensando... (puede tardar en hardware sin GPU)"):
            answer = send_to_assistant(prompt)
        st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})

with st.sidebar:
    st.subheader("Configuración")
    st.text_input("URL del asistente", value=ASSISTANT_URL, disabled=True)
    st.caption(
        "🎙️ STT: usa el micrófono del navegador (Web Speech API) o Whisper vía Ollama.\n\n"
        "🔊 TTS: se reproduce en el cliente o mediante espeak/pyttsx3 en el backend."
    )
    if st.button("Nueva conversación"):
        st.session_state.messages = []
        st.session_state.session_id = str(uuid.uuid4())
        st.rerun()
