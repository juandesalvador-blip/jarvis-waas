#!/usr/bin/env python3
"""
jarvis_manager.py – Orquestador de la infraestructura Docker de Jarvis
(AI Workforce as a Service).

Automatiza la ejecución de los contenedores definidos en `docker-compose.yml`
respetando el orden de dependencias descrito en la arquitectura:

    Nivel 0 (sin dependencias):  postgres, neo4j, redis, minio, ollama, prometheus
    Nivel 1 (dependen de N0):    n8n (postgres, redis) · grafana (prometheus)
    Nivel 2 (dependen de N1):    streamlit-ui (n8n)

Para cada servicio se ejecuta un chequeo de salud real (HTTP o `exec` dentro
del contenedor) en vez de confiar solo en el estado "Up" de Docker, de forma
que el script solo continúa con el siguiente nivel cuando el anterior está
realmente listo para recibir tráfico.

Uso:
    python scripts/jarvis_manager.py doctor
    python scripts/jarvis_manager.py up [servicio ...] [--no-build] [--timeout 180]
    python scripts/jarvis_manager.py down [--volumes]
    python scripts/jarvis_manager.py restart <servicio>
    python scripts/jarvis_manager.py status
    python scripts/jarvis_manager.py logs <servicio> [--follow] [--tail 200]
    python scripts/jarvis_manager.py init-db
    python scripts/jarvis_manager.py pull-models
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import requests
from dotenv import dotenv_values

# En consolas "legacy" de Windows (cmd.exe / PowerShell sin soporte UTF-8) la
# codificación por defecto puede ser cp1252, lo que rompe al imprimir tildes
# o símbolos. Forzamos UTF-8 en stdout/stderr para evitar UnicodeEncodeError.
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

try:
    from rich.console import Console
    from rich.table import Table
except ImportError:  # pragma: no cover - rich es opcional en tiempo de import
    Console = None  # type: ignore
    Table = None  # type: ignore

ROOT_DIR = Path(__file__).resolve().parent.parent
COMPOSE_FILE = ROOT_DIR / "docker-compose.yml"
ENV_FILE = ROOT_DIR / ".env"
ENV_EXAMPLE_FILE = ROOT_DIR / ".env.example"

console = Console(legacy_windows=False) if Console else None


def log(msg: str, style: str = "") -> None:
    if console:
        console.print(msg, style=style or None)
    else:
        print(msg)


def env(name: str, default: str = "") -> str:
    """Lee una variable primero del .env del proyecto y luego del entorno del SO."""
    values = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
    return values.get(name) or os.environ.get(name) or default


@dataclass
class Service:
    name: str
    description: str
    depends_on: list[str] = field(default_factory=list)
    check: Optional[Callable[[], bool]] = None
    startup_hint: str = ""


def http_ok(url: str, timeout: float = 3.0) -> bool:
    try:
        resp = requests.get(url, timeout=timeout)
        return resp.status_code < 500
    except requests.exceptions.RequestException:
        return False


def tcp_ok(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def exec_ok(service: str, *cmd: str) -> bool:
    result = compose_run(["exec", "-T", service, *cmd], capture=True, check=False)
    return result.returncode == 0


def container_running(service: str) -> bool:
    """Verifica que el contenedor de ESTE proyecto (no otro que use el mismo
    puerto en la máquina) esté realmente corriendo, antes de confiar en un
    chequeo de red por puerto."""
    result = compose_run(["ps", "-q", service], capture=True)
    container_id = (result.stdout or "").strip().splitlines()
    if not container_id:
        return False
    inspect = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", container_id[0]],
        capture_output=True,
        text=True,
    )
    return inspect.stdout.strip() == "true"


def build_services() -> dict[str, Service]:
    postgres_user = env("POSTGRES_USER", "jarvis")
    postgres_port = int(env("POSTGRES_PORT", "5432"))
    redis_port = int(env("REDIS_PORT", "6379"))
    neo4j_http_port = env("NEO4J_HTTP_PORT", "7474")
    minio_api_port = env("MINIO_API_PORT", "9000")
    ollama_port = env("OLLAMA_PORT", "11434")
    n8n_port = env("N8N_PORT", "5678")
    prometheus_port = env("PROMETHEUS_PORT", "9090")
    grafana_port = env("GRAFANA_PORT", "3000")
    streamlit_port = env("STREAMLIT_PORT", "8501")

    services: dict[str, Service] = {
        "postgres": Service(
            "postgres",
            "Base de datos estructurada (clientes, deudas, mensajes, tareas)",
            check=lambda: container_running("postgres")
            and (exec_ok("postgres", "pg_isready", "-U", postgres_user) or tcp_ok("localhost", postgres_port)),
        ),
        "neo4j": Service(
            "neo4j",
            "Knowledge Graph (Persona/Conocimiento/Actividad)",
            check=lambda: container_running("neo4j") and http_ok(f"http://localhost:{neo4j_http_port}"),
            startup_hint="Neo4j puede tardar ~30s en la primera carga.",
        ),
        "redis": Service(
            "redis",
            "Cache / colas de trabajo / rate-limiting",
            check=lambda: container_running("redis") and tcp_ok("localhost", redis_port),
        ),
        "minio": Service(
            "minio",
            "Almacenamiento S3-compatible (PDF, audio, imágenes)",
            check=lambda: container_running("minio")
            and http_ok(f"http://localhost:{minio_api_port}/minio/health/live"),
        ),
        "ollama": Service(
            "ollama",
            "Runtime de LLMs locales (Qwen, Kimi, Llama, Mistral)",
            check=lambda: container_running("ollama") and http_ok(f"http://localhost:{ollama_port}/api/tags"),
            startup_hint="La primera descarga de modelos puede tardar varios minutos.",
        ),
        "prometheus": Service(
            "prometheus",
            "Recolección de métricas",
            check=lambda: container_running("prometheus")
            and http_ok(f"http://localhost:{prometheus_port}/-/healthy"),
        ),
        "n8n": Service(
            "n8n",
            "Workflow engine (ingress, classifier, router, agentes)",
            depends_on=["postgres", "redis"],
            check=lambda: container_running("n8n") and http_ok(f"http://localhost:{n8n_port}/healthz"),
            startup_hint="n8n espera a que PostgreSQL esté listo antes de migrar su esquema.",
        ),
        "grafana": Service(
            "grafana",
            "Dashboards de monitoreo",
            depends_on=["prometheus"],
            check=lambda: container_running("grafana") and http_ok(f"http://localhost:{grafana_port}/api/health"),
        ),
        "streamlit-ui": Service(
            "streamlit-ui",
            "Frontend de chat con voz (STT/TTS)",
            depends_on=["n8n"],
            check=lambda: container_running("streamlit-ui")
            and http_ok(f"http://localhost:{streamlit_port}/_stcore/health"),
        ),
    }
    return services


def topological_levels(services: dict[str, Service]) -> list[list[str]]:
    """Agrupa los servicios en niveles: cada nivel solo depende de niveles previos."""
    remaining = dict(services)
    levels: list[list[str]] = []
    resolved: set[str] = set()

    while remaining:
        level = [
            name
            for name, svc in remaining.items()
            if all(dep in resolved for dep in svc.depends_on)
        ]
        if not level:
            raise RuntimeError(
                f"Dependencia circular o no resuelta entre: {list(remaining)}"
            )
        levels.append(sorted(level))
        for name in level:
            resolved.add(name)
            remaining.pop(name)
    return levels


# -----------------------------------------------------------------------------
# Wrappers de `docker compose`
# -----------------------------------------------------------------------------

_compose_base: Optional[list[str]] = None


def compose_base() -> list[str]:
    global _compose_base
    if _compose_base is not None:
        return _compose_base

    if shutil.which("docker") and subprocess.run(
        ["docker", "compose", "version"],
        capture_output=True,
    ).returncode == 0:
        _compose_base = ["docker", "compose"]
    elif shutil.which("docker-compose"):
        _compose_base = ["docker-compose"]
    else:
        log(
            "[red]No se encontró 'docker compose' ni 'docker-compose' en el PATH.[/red]"
            if console
            else "ERROR: No se encontró 'docker compose' ni 'docker-compose' en el PATH.",
        )
        sys.exit(1)
    return _compose_base


def compose_run(
    args: list[str], capture: bool = False, check: bool = False
) -> subprocess.CompletedProcess:
    """Ejecuta `docker compose <args>`. Nunca lanza excepción; el llamador
    decide qué hacer con `returncode` (o pasa check=True para propagarlo)."""
    cmd = [*compose_base(), "-f", str(COMPOSE_FILE), "--project-directory", str(ROOT_DIR), *args]
    result = subprocess.run(
        cmd, cwd=ROOT_DIR, capture_output=capture, text=True,
        encoding="utf-8", errors="replace",
    )
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
    return result


# -----------------------------------------------------------------------------
# Comandos
# -----------------------------------------------------------------------------


def cmd_doctor(_args: argparse.Namespace) -> None:
    log("[bold]Jarvis · Diagnóstico del entorno[/bold]" if console else "Jarvis · Diagnóstico del entorno")

    ok = True

    if shutil.which("docker") is None:
        log("[red][FAIL] Docker no está instalado o no está en el PATH.[/red]")
        ok = False
    else:
        info = subprocess.run(["docker", "info"], capture_output=True, text=True)
        if info.returncode != 0:
            log("[red][FAIL] El daemon de Docker no está corriendo (docker info falló).[/red]")
            ok = False
        else:
            log("[green][OK] Docker está instalado y el daemon responde.[/green]")

    compose_base()  # sys.exit si no existe
    log("[green][OK] 'docker compose' disponible.[/green]")

    if not ENV_FILE.exists():
        log(
            "[yellow]! No existe .env — se usará .env.example como base al ejecutar comandos.[/yellow]"
        )
    else:
        log("[green][OK] Archivo .env encontrado.[/green]")

    for path in [
        COMPOSE_FILE,
        ROOT_DIR / "config" / "postgres" / "init.sql",
        ROOT_DIR / "config" / "neo4j" / "init.cypher",
        ROOT_DIR / "config" / "prometheus" / "prometheus.yml",
        ROOT_DIR / "frontend" / "Dockerfile",
    ]:
        if path.exists():
            log(f"[green][OK] {path.relative_to(ROOT_DIR)}[/green]")
        else:
            log(f"[red][FAIL] Falta {path.relative_to(ROOT_DIR)}[/red]")
            ok = False

    if not ok:
        log("[red]Corrige los puntos anteriores antes de continuar.[/red]")
        sys.exit(1)
    log("[bold green]Entorno listo para 'up'.[/bold green]")


def ensure_env_file() -> None:
    if not ENV_FILE.exists() and ENV_EXAMPLE_FILE.exists():
        ENV_FILE.write_text(ENV_EXAMPLE_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        log("[yellow]Se creó .env a partir de .env.example (revisa las contraseñas por defecto).[/yellow]")


def wait_for_health(service: Service, timeout: int) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            if service.check is None or service.check():
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def cmd_up(args: argparse.Namespace) -> None:
    ensure_env_file()
    services = build_services()
    target = set(args.services) if args.services else set(services)

    unknown = target - set(services)
    if unknown:
        log(f"[red]Servicios desconocidos: {', '.join(unknown)}[/red]")
        sys.exit(1)

    if not args.no_build and "streamlit-ui" in target:
        log("[bold]Construyendo imágenes locales (streamlit-ui)...[/bold]")
        compose_run(["build", "streamlit-ui"])

    pullable = sorted(target - {"streamlit-ui"})
    if pullable:
        log(f"[bold]Descargando imágenes (docker compose pull): {', '.join(pullable)}[/bold]")
        compose_run(["pull", "--ignore-pull-failures", *pullable])

    levels = topological_levels(services)
    for level in levels:
        level_targets = [name for name in level if name in target]
        if not level_targets:
            continue

        log(f"\n[bold cyan]-> Iniciando nivel: {', '.join(level_targets)}[/bold cyan]")
        compose_run(["up", "-d", *level_targets])

        for name in level_targets:
            svc = services[name]
            log(f"  Esperando a que '{name}' esté saludable... ({svc.description})")
            if svc.startup_hint:
                log(f"    [dim]{svc.startup_hint}[/dim]")
            healthy = wait_for_health(svc, args.timeout)
            if healthy:
                log(f"  [green][OK] {name} listo.[/green]")
            else:
                log(
                    f"  [red][FAIL] {name} no respondió healthy en {args.timeout}s. "
                    f"Revisa: docker compose logs {name}[/red]"
                )
                sys.exit(1)

    log("\n[bold green]Jarvis está arriba. Accesos rápidos:[/bold green]")
    print_access_urls()


def print_access_urls() -> None:
    rows = [
        ("Streamlit UI (chat)", f"http://localhost:{env('STREAMLIT_PORT','8501')}"),
        ("n8n (workflows)", f"http://localhost:{env('N8N_PORT','5678')}"),
        ("Neo4j Browser", f"http://localhost:{env('NEO4J_HTTP_PORT','7474')}"),
        ("MinIO Console", f"http://localhost:{env('MINIO_CONSOLE_PORT','9001')}"),
        ("Grafana", f"http://localhost:{env('GRAFANA_PORT','3000')}"),
        ("Prometheus", f"http://localhost:{env('PROMETHEUS_PORT','9090')}"),
        ("Ollama API", f"http://localhost:{env('OLLAMA_PORT','11434')}"),
    ]
    for label, url in rows:
        log(f"  - {label}: {url}")


def cmd_down(args: argparse.Namespace) -> None:
    cmd = ["down"]
    if args.volumes:
        cmd.append("-v")
        log("[yellow]Se eliminarán también los volúmenes (todos los datos).[/yellow]")
    compose_run(cmd)
    log("[green]Contenedores detenidos.[/green]")


def cmd_restart(args: argparse.Namespace) -> None:
    services = build_services()
    if args.service not in services:
        log(f"[red]Servicio desconocido: {args.service}[/red]")
        sys.exit(1)
    compose_run(["restart", args.service])
    svc = services[args.service]
    log(f"Esperando a que '{args.service}' vuelva a estar saludable...")
    if wait_for_health(svc, args.timeout):
        log(f"[green][OK] {args.service} reiniciado y saludable.[/green]")
    else:
        log(f"[red][FAIL] {args.service} no respondió healthy tras el reinicio.[/red]")
        sys.exit(1)


def cmd_status(_args: argparse.Namespace) -> None:
    services = build_services()
    result = compose_run(["ps", "--format", "table"], capture=True)
    log(result.stdout or result.stderr)

    if Table:
        table = Table(title="Salud de servicios (chequeo activo)")
        table.add_column("Servicio")
        table.add_column("Descripción")
        table.add_column("Salud")
        for name, svc in services.items():
            try:
                healthy = bool(svc.check and svc.check())
            except Exception:
                healthy = False
            status = "[green]OK[/green]" if healthy else "[red]DOWN[/red]"
            table.add_row(name, svc.description, status)
        console.print(table)
    else:
        for name, svc in services.items():
            try:
                healthy = bool(svc.check and svc.check())
            except Exception:
                healthy = False
            print(f"  {name:15s} {'OK' if healthy else 'DOWN':6s} {svc.description}")


def cmd_logs(args: argparse.Namespace) -> None:
    cmd = ["logs", "--tail", str(args.tail)]
    if args.follow:
        cmd.append("-f")
    cmd.append(args.service)
    subprocess.run([*compose_base(), "-f", str(COMPOSE_FILE), *cmd], cwd=ROOT_DIR)


def cmd_init_db(_args: argparse.Namespace) -> None:
    log("[bold]Inicializando esquemas de bases de datos...[/bold]")

    log("PostgreSQL: el esquema se aplica automáticamente en el primer arranque "
        "(config/postgres/init.sql). Verificando tablas...")
    pg_user = env("POSTGRES_USER", "jarvis")
    pg_db = env("POSTGRES_DB", "jarvis")
    result = compose_run(
        ["exec", "-T", "postgres", "psql", "-U", pg_user, "-d", pg_db, "-c", "\\dt"],
        capture=True,
    )
    log(result.stdout or result.stderr)

    log("\nNeo4j: aplicando config/neo4j/init.cypher...")
    if not container_running("neo4j"):
        log("[yellow]! El servicio 'neo4j' no está corriendo, omitiendo. "
            "Ejecuta 'up neo4j' primero.[/yellow]")
        return
    neo4j_password = env("NEO4J_PASSWORD", "changeme123")
    compose_run(["cp", "config/neo4j/init.cypher", "neo4j:/tmp/init.cypher"])
    result = compose_run(
        [
            "exec", "-T", "neo4j", "cypher-shell",
            "-u", "neo4j", "-p", neo4j_password,
            "-f", "/tmp/init.cypher",
        ],
        capture=True,
    )
    log(result.stdout or result.stderr)
    log("[green]Inicialización de bases de datos completada.[/green]")


def cmd_pull_models(_args: argparse.Namespace) -> None:
    models = [m.strip() for m in env("OLLAMA_MODELS", "qwen2.5:7b").split(",") if m.strip()]
    for model in models:
        log(f"[bold]Descargando modelo Ollama: {model}[/bold]")
        subprocess.run(
            [*compose_base(), "-f", str(COMPOSE_FILE), "exec", "-T", "ollama", "ollama", "pull", model],
            cwd=ROOT_DIR,
        )
    log("[green]Descarga de modelos completada.[/green]")


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Orquestador de contenedores Docker para Jarvis (AI-WaaS)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Verifica prerequisitos (Docker, compose, archivos).").set_defaults(
        func=cmd_doctor
    )

    p_up = sub.add_parser("up", help="Levanta los contenedores en el orden correcto.")
    p_up.add_argument("services", nargs="*", help="Servicios específicos (por defecto: todos).")
    p_up.add_argument("--timeout", type=int, default=180, help="Timeout de health-check por servicio (s).")
    p_up.add_argument("--no-build", action="store_true", help="No reconstruir la imagen de streamlit-ui.")
    p_up.set_defaults(func=cmd_up)

    p_down = sub.add_parser("down", help="Detiene y elimina los contenedores.")
    p_down.add_argument("--volumes", action="store_true", help="También elimina los volúmenes (datos).")
    p_down.set_defaults(func=cmd_down)

    p_restart = sub.add_parser("restart", help="Reinicia un servicio y espera a que esté saludable.")
    p_restart.add_argument("service")
    p_restart.add_argument("--timeout", type=int, default=120)
    p_restart.set_defaults(func=cmd_restart)

    sub.add_parser("status", help="Muestra el estado y la salud de cada servicio.").set_defaults(
        func=cmd_status
    )

    p_logs = sub.add_parser("logs", help="Muestra logs de un servicio.")
    p_logs.add_argument("service")
    p_logs.add_argument("--follow", "-f", action="store_true")
    p_logs.add_argument("--tail", type=int, default=200)
    p_logs.set_defaults(func=cmd_logs)

    sub.add_parser(
        "init-db", help="Aplica los esquemas iniciales de PostgreSQL y Neo4j."
    ).set_defaults(func=cmd_init_db)

    sub.add_parser(
        "pull-models", help="Descarga los modelos de Ollama definidos en OLLAMA_MODELS."
    ).set_defaults(func=cmd_pull_models)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
