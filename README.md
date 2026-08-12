# Jarvis – AI Workforce as a Service (AI-WaaS)

Jarvis empieza **compacto** y crece solo cuando se necesita.

El **núcleo compacto** (siempre activo) es lo mínimo para tener un
asistente de IA local funcionando de punta a punta:

- **Ollama** – runtime de LLMs locales (modelo pequeño por defecto: `qwen2.5:3b`).
- **jarvis-assistant** – microservicio (FastAPI + [CrewAI](https://docs.crewai.com/),
  1 agente) con memoria de conversación en SQLite.
- **streamlit-ui** – chat web que habla directo con el asistente.

Los **extras** (PostgreSQL, Neo4j, MinIO, Redis, n8n, Prometheus, Grafana)
existen en `docker-compose.yml` pero **no se levantan por defecto**: se
activan explícitamente cuando una funcionalidad concreta los necesita
(ver [«Cuándo agregar cada extra»](#cuándo-agregar-cada-extra)).

Toda la ejecución de contenedores se automatiza con
[`scripts/jarvis_manager.py`](scripts/jarvis_manager.py), que:

- Por defecto levanta **solo el núcleo compacto**, en el orden correcto
  de dependencias y esperando a que cada servicio esté **realmente
  saludable** (HTTP/exec health-check), no solo "Up" en Docker.
- Permite levantar extras específicos por nombre, o todo con `--all`.
- Aplica los esquemas iniciales de PostgreSQL/Neo4j (cuando están
  activos), descarga modelos de Ollama, muestra logs, y da un reporte de
  estado consolidado.

## Estructura del proyecto

```
jarvis-waas/
├── docker-compose.yml          # Núcleo compacto + servicios "extras" (profile: extras)
├── .env.example                # Variables de entorno (copiar a .env)
├── requirements.txt            # Dependencias del script de orquestación
├── scripts/
│   └── jarvis_manager.py       # Orquestador Python (CLI)
├── config/
│   ├── postgres/init.sql       # Esquema (extra): users, conversations, messages, ...
│   ├── neo4j/init.cypher       # Constraints + nodos de ejemplo del grafo (extra)
│   ├── prometheus/prometheus.yml   # (extra)
│   ├── grafana/provisioning/        # (extra)
│   └── n8n/workflows/               # Workflow de ejemplo para cuando se active n8n (extra)
├── assistant/                   # Microservicio del Asistente General (CrewAI + FastAPI)
│   ├── crew.py                 # Agente único + su tarea (LLM vía Ollama)
│   ├── storage.py              # Memoria de conversación en SQLite (sin contenedor extra)
│   ├── app.py                  # API HTTP (/assist, /health)
│   ├── Dockerfile
│   └── tests/                  # Pruebas unitarias (pytest, sin depender de Ollama real)
└── frontend/                   # Chat UI (Streamlit) + Dockerfile
```

## Requisitos

- Docker Desktop (o Docker Engine + Compose plugin) instalado y corriendo.
- Python 3.10+ (solo para ejecutar el script de orquestación; los
  servicios en sí corren dentro de contenedores).

## Puesta en marcha (núcleo compacto)

```powershell
# 1. Clonar/copiar el proyecto y entrar a la carpeta
cd jarvis-waas

# 2. Instalar las dependencias del orquestador
python -m pip install -r requirements.txt

# 3. Copiar y ajustar las variables de entorno (contraseñas, puertos, etc.)
Copy-Item .env.example .env
# Edita .env y cambia TODAS las contraseñas "changeme*"

# 4. Verificar que Docker/Compose están listos
python scripts/jarvis_manager.py doctor

# 5. Levantar el núcleo compacto: ollama + jarvis-assistant + streamlit-ui
python scripts/jarvis_manager.py up

# 6. Descargar el modelo de Ollama (qwen2.5:3b por defecto)
python scripts/jarvis_manager.py pull-models
```

Al finalizar `up`, el script imprime los accesos rápidos del núcleo:

| Servicio                   | URL                         |
|-----------------------------|------------------------------|
| Streamlit UI (chat)         | http://localhost:8501       |
| Ollama API                  | http://localhost:11434      |
| Asistente General (CrewAI)  | http://localhost:8600/docs  |

## Comandos disponibles

```powershell
python scripts/jarvis_manager.py doctor                 # Verifica prerequisitos
python scripts/jarvis_manager.py up                      # Solo el núcleo compacto
python scripts/jarvis_manager.py up --all                 # Núcleo + todos los extras
python scripts/jarvis_manager.py up n8n postgres redis     # Extras específicos (con sus dependencias)
python scripts/jarvis_manager.py up --no-build            # Sin reconstruir imágenes locales
python scripts/jarvis_manager.py up --timeout 300         # Timeout de health-check (s)
python scripts/jarvis_manager.py status                  # Estado + salud de cada servicio
python scripts/jarvis_manager.py logs jarvis-assistant --follow  # Logs en vivo de un servicio
python scripts/jarvis_manager.py restart jarvis-assistant  # Reinicia y espera a que sane
python scripts/jarvis_manager.py init-db                 # Aplica esquemas Postgres/Neo4j (si están activos)
python scripts/jarvis_manager.py pull-models              # Descarga modelos de Ollama
python scripts/jarvis_manager.py down                    # Detiene los contenedores levantados
python scripts/jarvis_manager.py down --volumes          # Detiene y borra TODOS los datos
```

Al pedir un extra por nombre (por ejemplo `up n8n`), el script resuelve
automáticamente sus dependencias (`postgres`, `redis`, `jarvis-assistant`)
y espera a que cada una esté saludable antes de continuar.

## Orden de arranque (niveles de dependencia)

```
Núcleo compacto:
  Nivel 0: ollama
  Nivel 1: jarvis-assistant (← ollama)
  Nivel 2: streamlit-ui (← jarvis-assistant)

Extras (opt-in):
  Nivel 0: postgres · neo4j · redis · minio · prometheus
  Nivel 1: n8n (← postgres, redis, jarvis-assistant)   grafana (← prometheus)
```

## Cuándo agregar cada extra

No agregues un extra "por si acaso": cada contenedor consume RAM/CPU que
en hardware modesto (sin GPU) compite directamente con la inferencia de
Ollama. Agrégalo solo cuando la funcionalidad concreta lo requiera:

| Extra                  | Agrégalo cuando...                                                        |
|-------------------------|----------------------------------------------------------------------------|
| **postgres**            | Necesites memoria estructurada multi-usuario más allá del historial simple en SQLite del asistente (clientes, tareas, métricas). |
| **neo4j**               | Construyas features de knowledge graph reales (relaciones Persona/Conocimiento/Actividad). |
| **redis**               | Necesites colas de trabajo reales o rate-limiting entre servicios.        |
| **minio**               | El asistente deba manejar archivos (PDFs, audio, imágenes) como entrada o salida. |
| **n8n**                 | Integres canales externos (WhatsApp/Telegram/Twilio) o flujos visuales multi-agente. |
| **prometheus/grafana**  | Haya suficiente tráfico real como para justificar dashboards de monitoreo. |

Para activarlos: `python scripts/jarvis_manager.py up <extra>` o
`--all` para todo. Los datos de cada extra persisten en su propio volumen
Docker aunque lo detengas con `down` (sin `--volumes`).

## Asistente General (CrewAI)

El servicio `jarvis-assistant` (carpeta [`assistant/`](assistant/)) es un
**agente único** construido con [CrewAI](https://docs.crewai.com/) que usa
el propio Ollama de la infraestructura como LLM (sin depender de ninguna
API de pago), con memoria de conversación por usuario guardada en un
archivo SQLite (`storage.py`, sin contenedor extra).

> Empezó como un equipo de 3 agentes secuenciales (Planificador →
> Investigador → Redactor). Se simplificó a 1 agente para respuestas más
> rápidas en CPU; si una tarea concreta necesita pasos intermedios reales
> (p. ej. investigación multi-fuente), se puede volver a un Crew de
> varios agentes sin cambiar la interfaz pública del módulo (`run_assistant`).

Se expone como un **microservicio HTTP** (FastAPI):

- `GET  /health` → chequeo de salud (usado por `jarvis_manager.py status`).
- `POST /assist` → `{"message": "...", "user_id": "...", "language": "es"}`
  devuelve `{"response_text": "...", "success": true, "latency_ms": 1234}`.
  El historial reciente de `user_id` se usa automáticamente como contexto.

### Ejecutar las pruebas del asistente

Las pruebas usan mocks para `Crew.kickoff` y SQLite en archivos temporales,
por lo que **no requieren tener Ollama corriendo** ni la stack levantada:

```powershell
python -m pip install -r assistant/requirements-dev.txt
python -m pytest assistant/tests -v
```

### Probar el microservicio manualmente

```powershell
python scripts/jarvis_manager.py up
python scripts/jarvis_manager.py pull-models   # asegura que el modelo esté descargado

curl -X POST http://localhost:8600/assist `
  -H "Content-Type: application/json" `
  -d '{\"message\": \"Explícame en 2 líneas qué es Jarvis\", \"user_id\": \"juan\"}'
```

## Activar n8n para integraciones multi-canal (extra)

Cuando necesites conectar WhatsApp/Telegram/Twilio, activa n8n:

```powershell
python scripts/jarvis_manager.py up n8n
```

1. Abre http://localhost:5678 y accede con `N8N_BASIC_AUTH_USER` /
   `N8N_BASIC_AUTH_PASSWORD` (definidos en `.env`).
2. Configura las credenciales de Twilio/Telegram en **Credentials**.
3. Importa el workflow [`config/n8n/workflows/asistente_general.json`](config/n8n/workflows/asistente_general.json)
   (menú **Workflows → Import from File**): expone el webhook `jarvis-chat`
   y lo conecta con `jarvis-assistant` (`/assist`) y una respuesta al usuario.

## Notas de seguridad (Habeas Data)

- Cambia **todas** las contraseñas por defecto en `.env` antes de exponer
  cualquier puerto fuera de `localhost`.
- Si activas `postgres`, su esquema incluye la tabla `communications` para
  registrar el consentimiento de grabación, y `agent_logs` para auditoría.
- Considera poner n8n y Grafana (si los activas) detrás de un reverse
  proxy con TLS (Traefik/Caddy) si se despliega en un VPS público.

## Solución de problemas

- `python scripts/jarvis_manager.py status` muestra tanto el estado de
  Docker (`docker compose ps`) como un chequeo de salud real por servicio.
- `python scripts/jarvis_manager.py logs <servicio> --follow` para ver
  logs en vivo si un servicio no queda "healthy" dentro del timeout.
- En CPU sin GPU, la primera respuesta del asistente puede tardar mientras
  Ollama carga el modelo en memoria; las siguientes son más rápidas. Si
  las respuestas tardan demasiado, revisa cuántos otros contenedores/apps
  están compitiendo por CPU/RAM y considera un modelo aún más pequeño
  (ajusta `OLLAMA_ASSISTANT_MODEL` y `OLLAMA_MODELS` en `.env`).
