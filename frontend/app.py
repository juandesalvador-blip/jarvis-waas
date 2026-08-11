"""
Jarvis – Frontend de chat (Streamlit)

Interfaz de chat que envía los mensajes del usuario al webhook de n8n
(Ingress) y muestra la respuesta del agente correspondiente. El soporte
de voz (STT/TTS) real depende de las capacidades del navegador (Web
Speech API) y de las librerías locales (pyttsx3); aquí se deja el punto
de integración documentado en `speak()` y en el widget de audio.
"""

import os
import uuid

import requests
import streamlit as st

N8N_WEBHOOK_URL = os.environ.get(
    "N8N_WEBHOOK_URL", "http://n8n:5678/webhook/jarvis-chat"
)

st.set_page_config(page_title="Jarvis – AI Workforce", page_icon="🤖", layout="centered")
st.title("🤖 Jarvis – AI Workforce as a Service")
st.caption("Chat conectado a n8n · agentes: TUTOR · COBRANZA · CITAS · SOPORTE")

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []


def send_to_n8n(text: str) -> str:
    """Envía el mensaje al webhook de n8n y devuelve la respuesta del agente."""
    payload = {
        "user_id": st.session_state.session_id,
        "channel": "web",
        "text": text,
        "language": "es",
    }
    try:
        resp = requests.post(N8N_WEBHOOK_URL, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get("response_text", "(sin respuesta del agente)")
    except requests.exceptions.RequestException as exc:
        return f"⚠️ No se pudo contactar a n8n: {exc}"


for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

prompt = st.chat_input("Escribe tu mensaje...")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Jarvis está pensando..."):
            answer = send_to_n8n(prompt)
        st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})

with st.sidebar:
    st.subheader("Configuración")
    st.text_input("Webhook n8n", value=N8N_WEBHOOK_URL, disabled=True)
    st.caption(
        "🎙️ STT: usa el micrófono del navegador (Web Speech API) o Whisper vía Ollama.\n\n"
        "🔊 TTS: se reproduce en el cliente o mediante espeak/pyttsx3 en el backend."
    )
    if st.button("Nueva conversación"):
        st.session_state.messages = []
        st.session_state.session_id = str(uuid.uuid4())
        st.rerun()
