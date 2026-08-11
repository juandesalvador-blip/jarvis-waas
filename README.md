# Jarvis – AI Workforce as a Service (AI-WaaS)

Infraestructura Docker completa para la plataforma Jarvis descrita en el
informe de arquitectura: orquestación de agentes de IA (cobranza,
cualificación de leads, citas, soporte) vía **n8n**, con **PostgreSQL**
(datos estructurados), **Neo4j** (knowledge graph), **MinIO** (S3-compatible),
**Redis** (cache/colas), **Ollama** (LLMs locales), **Prometheus + Grafana**
(monitoreo), un **Asistente General multi-agente con CrewAI** y un frontend
de chat con voz en **Streamlit**.

Toda la ejecución de contenedores se automatiza con
[`scripts/jarvis_manager.py`](scripts/jarvis_manager.py), que:

- Arranca los servicios **en el orden correcto de dependencias** (por
  niveles, no todos a la vez): primero la infraestructura base
  (PostgreSQL, Neo4j, Redis, MinIO, Ollama, Prometheus), luego lo que
  depende de ella (n8n, Grafana) y por último el frontend (Streamlit).
- Espera a que cada servicio esté **realmente saludable** (HTTP/exec
  health-check), no solo "Up" en Docker, antes de continuar con el
  siguiente nivel.
- Aplica los esquemas iniciales de PostgreSQL/Neo4j, descarga modelos de
  Ollama, muestra logs, y da un reporte de estado consolidado.

## Estructura del proyecto

```
jarvis-waas/
├── docker-compose.yml          # Definición de los servicios de la arquitectura
├── .env.example                # Variables de entorno (copiar a .env)
├── requirements.txt            # Dependencias del script de orquestación (+ CrewAI)
├── scripts/
│   └── jarvis_manager.py       # Orquestador Python (CLI)
├── config/
│   ├── postgres/init.sql       # Esquema: users, conversations, messages,
│   │                           #   progress, tasks, agent_logs, daily_metrics,
│   │                           #   deudas, communications
│   ├── neo4j/init.cypher       # Constraints + nodos de ejemplo del grafo
│   ├── prometheus/prometheus.yml
│   ├── grafana/provisioning/   # Datasource (Prometheus) + dashboards
│   └── n8n/workflows/          # Workflows exportados, listos para importar en n8n
├── assistant/                   # Microservicio del Asistente General (CrewAI + FastAPI)
│   ├── crew.py                 # Agentes: Planificador · Investigador · Redactor
│   ├── app.py                  # API HTTP (/assist, /health) que consume n8n
│   ├── Dockerfile
│   └── tests/                  # Pruebas unitarias (pytest, sin depender de Ollama real)
└── frontend/                   # Chat UI (Streamlit) + Dockerfile
```

## Requisitos

- Docker Desktop (o Docker Engine + Compose plugin) instalado y corriendo.
- Python 3.10+ (solo para ejecutar el script de orquestación; los
  servicios en sí corren dentro de contenedores).

## Puesta en marcha

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

# 5. Levantar toda la stack (build de streamlit-ui + pull + arranque por niveles)
python scripts/jarvis_manager.py up

# 6. Inicializar los esquemas de PostgreSQL y Neo4j
python scripts/jarvis_manager.py init-db

# 7. (Opcional) Descargar modelos de Ollama definidos en OLLAMA_MODELS
python scripts/jarvis_manager.py pull-models
```

Al finalizar `up`, el script imprime los accesos rápidos:

| Servicio             | URL                              |
|-----------------------|-----------------------------------|
| Streamlit UI (chat)   | http://localhost:8501            |
| n8n (workflows)       | http://localhost:5678            |
| Neo4j Browser         | http://localhost:7474            |
| MinIO Console         | http://localhost:9001            |
| Grafana               | http://localhost:3000            |
| Prometheus            | http://localhost:9090            |
| Ollama API            | http://localhost:11434           |
| Asistente General (CrewAI) | http://localhost:8600/docs |

## Comandos disponibles

```powershell
python scripts/jarvis_manager.py doctor                 # Verifica prerequisitos
python scripts/jarvis_manager.py up [servicio ...]       # Levanta todo o servicios específicos
python scripts/jarvis_manager.py up --no-build           # Sin reconstruir streamlit-ui
python scripts/jarvis_manager.py up --timeout 300        # Timeout de health-check (s)
python scripts/jarvis_manager.py status                  # Estado + salud de cada servicio
python scripts/jarvis_manager.py logs n8n --follow        # Logs en vivo de un servicio
python scripts/jarvis_manager.py restart postgres        # Reinicia y espera a que sane
python scripts/jarvis_manager.py init-db                 # Aplica esquemas Postgres/Neo4j
python scripts/jarvis_manager.py pull-models             # Descarga modelos de Ollama
python scripts/jarvis_manager.py down                    # Detiene los contenedores
python scripts/jarvis_manager.py down --volumes          # Detiene y borra TODOS los datos
```

Puedes levantar solo un subconjunto (el script respeta las dependencias
igualmente, por ejemplo `up n8n` primero espera a que `postgres` y `redis`
estén saludables si no lo están):

```powershell
python scripts/jarvis_manager.py up postgres redis minio
```

## Orden de arranque (niveles de dependencia)

```
Nivel 0: postgres · neo4j · redis · minio · ollama · prometheus
Nivel 1: jarvis-assistant (← ollama)   grafana (← prometheus)
Nivel 2: n8n (← postgres, redis, jarvis-assistant)
Nivel 3: streamlit-ui (← n8n)
```

## Asistente General (CrewAI)

El servicio `jarvis-assistant` (carpeta [`assistant/`](assistant/)) añade un
equipo de agentes colaborativos construido con [CrewAI](https://docs.crewai.com/)
que usa el propio Ollama de la infraestructura como LLM (sin depender de
ninguna API de pago):

| Agente         | Rol                                                              |
|----------------|-------------------------------------------------------------------|
| Planificador   | Desglosa la petición del usuario en pasos de investigación.       |
| Investigador   | Reúne los datos y argumentos relevantes para responder.           |
| Redactor       | Sintetiza todo en una respuesta final clara, en español.          |

Se expone como un **microservicio HTTP** (FastAPI) en lugar de un script
suelto, para que n8n lo invoque con un nodo "HTTP Request" sin necesitar
Python/CrewAI instalados dentro del contenedor de n8n:

- `GET  /health` → chequeo de salud (usado por `jarvis_manager.py status`).
- `POST /assist` → `{"message": "...", "user_id": "...", "language": "es"}`
  devuelve `{"response_text": "...", "success": true, "latency_ms": 1234}`.

### Ejecutar las pruebas del asistente

Las pruebas usan mocks para `Crew.kickoff`, por lo que **no requieren tener
Ollama corriendo** ni la stack levantada:

```powershell
python -m pip install -r assistant/requirements-dev.txt
python -m pytest assistant/tests -v
```

### Probar el microservicio manualmente

```powershell
python scripts/jarvis_manager.py up ollama jarvis-assistant
python scripts/jarvis_manager.py pull-models   # asegura que el modelo esté descargado

curl -X POST http://localhost:8600/assist `
  -H "Content-Type: application/json" `
  -d '{\"message\": \"Explícame en 2 líneas qué es Jarvis\"}'
```

## Configuración de workflows en n8n

1. Abre http://localhost:5678 y accede con `N8N_BASIC_AUTH_USER` /
   `N8N_BASIC_AUTH_PASSWORD` (definidos en `.env`).
2. Configura las credenciales de Twilio/Telegram en **Credentials**.
3. Importa el workflow [`config/n8n/workflows/asistente_general.json`](config/n8n/workflows/asistente_general.json)
   (menú **Workflows → Import from File**): expone el webhook `jarvis-chat`
   y lo conecta con `jarvis-assistant` (`/assist`) y una respuesta al usuario.
4. Para los demás workflows del informe (WF-03 Cobranza, classifier,
   AG-TUTOR, AG-COBRANZA, AG-CITAS, AG-SOPORTE, AG-GUARD), apunta el nodo
   LLM a `http://ollama:11434` como hasta ahora.
5. El webhook de ingress debe coincidir con `N8N_WEBHOOK_URL` usado por
   el frontend Streamlit (`frontend/app.py`).

## Notas de seguridad (Habeas Data)

- Cambia **todas** las contraseñas por defecto en `.env` antes de exponer
  cualquier puerto fuera de `localhost`.
- El esquema de PostgreSQL incluye la tabla `communications` para
  registrar el consentimiento de grabación, y `agent_logs` para
  auditoría, tal como exige el informe de arquitectura.
- Considera poner n8n y Grafana detrás de un reverse proxy con TLS
  (Traefik/Caddy) si se despliega en un VPS público.

## Solución de problemas

- `python scripts/jarvis_manager.py status` muestra tanto el estado de
  Docker (`docker compose ps`) como un chequeo de salud real por servicio.
- `python scripts/jarvis_manager.py logs <servicio> --follow` para ver
  logs en vivo si un servicio no queda "healthy" dentro del timeout.
- Si `neo4j` u `ollama` tardan más de lo normal en el primer arranque,
  usa `--timeout 300` o superior.
