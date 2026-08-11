-- =============================================================================
-- JARVIS – Esquema inicial de PostgreSQL
-- Se ejecuta automáticamente por el entrypoint de la imagen postgres la
-- primera vez que se crea el volumen de datos.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Clientes / contactos
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    full_name       TEXT,
    phone           TEXT UNIQUE,
    email           TEXT,
    channel         TEXT,               -- whatsapp | telegram | web | email
    language        TEXT DEFAULT 'es',
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Historial de conversaciones
CREATE TABLE IF NOT EXISTS conversations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    agent           TEXT,               -- AG-TUTOR | AG-COBRANZA | AG-CITAS | AG-SOPORTE | AG-GUARD
    started_at      TIMESTAMPTZ DEFAULT now(),
    ended_at        TIMESTAMPTZ
);

-- Mensajes individuales
CREATE TABLE IF NOT EXISTS messages (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    sender          TEXT,               -- user | agent
    text            TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Progreso (p.ej. nivel de aprendizaje por materia, para AG-TUTOR)
CREATE TABLE IF NOT EXISTS progress (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    subject         TEXT,
    level           NUMERIC DEFAULT 0,
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Tareas / recordatorios
CREATE TABLE IF NOT EXISTS tasks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    title           TEXT,
    due_at          TIMESTAMPTZ,
    status          TEXT DEFAULT 'pendiente',
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Auditoría de acciones de agentes
CREATE TABLE IF NOT EXISTS agent_logs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent           TEXT,
    prompt          TEXT,
    response        TEXT,
    tokens_used     INTEGER,
    latency_ms      INTEGER,
    success         BOOLEAN,
    error_message   TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- KPIs diarios
CREATE TABLE IF NOT EXISTS daily_metrics (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    metric_date     DATE UNIQUE,
    conversations_count INTEGER DEFAULT 0,
    messages_count      INTEGER DEFAULT 0,
    escalations_count   INTEGER DEFAULT 0,
    debts_recovered_cop NUMERIC DEFAULT 0
);

-- Deudas (workflow de cobranza WF-03)
CREATE TABLE IF NOT EXISTS deudas (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID REFERENCES users(id) ON DELETE CASCADE,
    monto               NUMERIC NOT NULL,
    fecha_vencimiento   DATE,
    segmento            TEXT,
    estado              TEXT DEFAULT 'pendiente', -- pendiente | promesa | pagada | escalada
    ultima_comunicacion TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT now()
);

-- Consentimiento / Habeas Data
CREATE TABLE IF NOT EXISTS communications (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID REFERENCES users(id) ON DELETE CASCADE,
    consentimiento      BOOLEAN DEFAULT false,
    automatizacion_pausada BOOLEAN DEFAULT false,
    created_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_deudas_estado ON deudas(estado);
CREATE INDEX IF NOT EXISTS idx_agent_logs_created ON agent_logs(created_at);
