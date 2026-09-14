-- =============================================================
-- MOTOS Y SERVICIOS DE COLOMBIA SAS
-- Schema principal del pipeline de priorización de leads
-- =============================================================

-- Extensiones
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "unaccent";

-- =============================================================
-- 1. EMPRESAS
-- Las 3 comercializadoras del grupo. Base del control de acceso.
-- =============================================================
CREATE TABLE IF NOT EXISTS empresas (
    empresa_id      VARCHAR(20) PRIMARY KEY,
    nombre          VARCHAR(100) NOT NULL,
    activa          BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================
-- 2. PUNTOS DE VENTA
-- =============================================================
CREATE TABLE IF NOT EXISTS puntos_venta (
    punto_venta_id  VARCHAR(20) PRIMARY KEY,
    empresa_id      VARCHAR(20) NOT NULL REFERENCES empresas(empresa_id),
    nombre          VARCHAR(100) NOT NULL,
    ciudad          VARCHAR(50),
    region          VARCHAR(50),   -- Antioquia, Bogotá, Costa Atlántica
    activo          BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================
-- 3. CATÁLOGO DE MOTOS
-- =============================================================
CREATE TABLE IF NOT EXISTS catalogo_motos (
    referencia_id       VARCHAR(30) PRIMARY KEY,
    marca               VARCHAR(30) NOT NULL,   -- Honda, Bajaj, Suzuki, AKT, Hero
    linea               VARCHAR(50) NOT NULL,
    cilindraje_cc       INTEGER,
    segmento            VARCHAR(30),            -- urbana, sport, trabajo, etc.
    precio_lista        NUMERIC(12,2),
    disponible          BOOLEAN DEFAULT TRUE,
    punto_venta_id      VARCHAR(20) REFERENCES puntos_venta(punto_venta_id),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================
-- 4. ASESORES
-- =============================================================
CREATE TABLE IF NOT EXISTS asesores (
    asesor_id           VARCHAR(20) PRIMARY KEY,
    empresa_id          VARCHAR(20) NOT NULL REFERENCES empresas(empresa_id),
    punto_venta_id      VARCHAR(20) NOT NULL REFERENCES puntos_venta(punto_venta_id),
    nombre              VARCHAR(100) NOT NULL,
    email               VARCHAR(100),
    capacidad_diaria    INTEGER DEFAULT 10,     -- leads máximos por día
    activo              BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================
-- 5. LEADS NORMALIZADOS
-- Tabla central. Un registro por lead deduplicado.
-- =============================================================
CREATE TABLE IF NOT EXISTS leads (
    lead_id                 VARCHAR(30) PRIMARY KEY,
    empresa_id              VARCHAR(20) NOT NULL REFERENCES empresas(empresa_id),
    punto_venta_id          VARCHAR(20) REFERENCES puntos_venta(punto_venta_id),

    -- Datos de contacto normalizados
    nombre_cliente          VARCHAR(100),
    telefono                VARCHAR(20),        -- formato E.164 (+573001234567)
    email                   VARCHAR(100),
    ciudad                  VARCHAR(50),        -- ciudad canónica

    -- Origen
    canal                   VARCHAR(20) NOT NULL CHECK (canal IN ('WhatsApp', 'Meta Ads', 'Formulario Web')),
    campania                VARCHAR(100),
    fecha_registro          TIMESTAMPTZ,

    -- Modelo de interés
    modelo_interes_texto    TEXT,               -- texto original del canal
    referencia_id           VARCHAR(30) REFERENCES catalogo_motos(referencia_id),  -- mapeado al catálogo

    -- Gestión
    estado_gestion          VARCHAR(30),
    fecha_primer_contacto   TIMESTAMPTZ,

    -- Deduplicación
    es_duplicado            BOOLEAN DEFAULT FALSE,
    lead_id_principal       VARCHAR(30),        -- apunta al lead canónico si es duplicado

    -- Trazabilidad del pipeline
    pipeline_run_id         UUID,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================
-- 6. CONVERSACIONES
-- Metadata de cada conversación de WhatsApp
-- =============================================================
CREATE TABLE IF NOT EXISTS conversaciones (
    conversacion_id     VARCHAR(30) PRIMARY KEY,
    lead_id             VARCHAR(30) REFERENCES leads(lead_id),
    canal               VARCHAR(20),
    fecha_inicio        TIMESTAMPTZ,
    total_mensajes      INTEGER,
    raw_json            JSONB,          -- conversación completa para auditoría
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================
-- 7. EXTRACCIÓN IA DE CONVERSACIONES
-- Lo que Claude extrae de cada conversación. Un registro por conversación.
-- =============================================================
CREATE TABLE IF NOT EXISTS conversacion_extracciones (
    extraccion_id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversacion_id         VARCHAR(30) NOT NULL REFERENCES conversaciones(conversacion_id),
    lead_id                 VARCHAR(30) REFERENCES leads(lead_id),

    -- 6 campos que pide el enunciado
    modelo_interes          VARCHAR(100),       -- modelo mencionado en la conversación
    presupuesto_cuota       NUMERIC(12,2),      -- cuota inicial o presupuesto mencionado
    forma_pago              VARCHAR(30),        -- contado, crédito, leasing, etc.
    intencion_declarada     VARCHAR(50),        -- alta, media, baja / compra inmediata, exploración
    objecion_principal      TEXT,               -- precio, trámites, no le convence el modelo, etc.
    pidio_cita_cotizacion   BOOLEAN,

    -- Metadatos de la extracción
    modelo_ia_usado         VARCHAR(50),        -- claude-haiku-4-5, gpt-4o-mini, etc.
    tokens_usados           INTEGER,
    confianza               VARCHAR(10),        -- alta, media, baja (autoevaluación del modelo)
    raw_response            JSONB,              -- respuesta completa del LLM para auditoría
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================
-- 8. SCORES DE LEADS
-- Una fila por lead por ejecución del pipeline.
-- =============================================================
CREATE TABLE IF NOT EXISTS lead_scores (
    score_id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id                 VARCHAR(30) NOT NULL REFERENCES leads(lead_id),
    pipeline_run_id         UUID,

    -- Score final
    score_total             NUMERIC(5,2),       -- 0 a 100
    temperatura             VARCHAR(10) CHECK (temperatura IN ('Caliente', 'Tibio', 'Frio')),

    -- Componentes del score (para explicabilidad)
    score_canal             NUMERIC(5,2),
    score_tiempo_respuesta  NUMERIC(5,2),
    score_cuota_inicial     NUMERIC(5,2),
    score_forma_pago        NUMERIC(5,2),
    score_intencion         NUMERIC(5,2),
    score_pidio_cita        NUMERIC(5,2),

    -- Justificación legible
    explicacion             TEXT,

    created_at              TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================
-- 9. ASIGNACIONES DIARIAS
-- A qué asesor queda asignado cada lead en cada ejecución.
-- =============================================================
CREATE TABLE IF NOT EXISTS lead_asignaciones (
    asignacion_id       UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id             VARCHAR(30) NOT NULL REFERENCES leads(lead_id),
    asesor_id           VARCHAR(20) NOT NULL REFERENCES asesores(asesor_id),
    pipeline_run_id     UUID,
    fecha_asignacion    DATE NOT NULL DEFAULT CURRENT_DATE,
    orden_prioridad     INTEGER,        -- posición en la lista del asesor ese día
    atendido            BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================
-- 10. HISTÓRICO DE CIERRES
-- Fuente de verdad para calibrar el scoring. Solo lectura en producción.
-- =============================================================
CREATE TABLE IF NOT EXISTS historico_cierres (
    historico_id                VARCHAR(30) PRIMARY KEY,
    canal                       VARCHAR(20),
    empresa_id                  VARCHAR(20) REFERENCES empresas(empresa_id),
    punto_venta_id              VARCHAR(20) REFERENCES puntos_venta(punto_venta_id),
    modelo_cotizado             VARCHAR(100),
    horas_primer_contacto       NUMERIC(6,2),
    num_contactos               INTEGER,
    manifesto_cuota_inicial     BOOLEAN,
    forma_pago_declarada        VARCHAR(30),
    pidio_cita                  BOOLEAN,
    desenlace                   VARCHAR(20) CHECK (desenlace IN ('Cerrado', 'Perdido', 'Sin gestión')),
    created_at                  TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================
-- 11. LOG DE EJECUCIONES DEL PIPELINE
-- =============================================================
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    iniciado_en         TIMESTAMPTZ DEFAULT NOW(),
    finalizado_en       TIMESTAMPTZ,
    estado              VARCHAR(20) CHECK (estado IN ('en_proceso', 'exitoso', 'fallido')),
    leads_procesados    INTEGER,
    leads_scoring       INTEGER,
    leads_asignados     INTEGER,
    error_mensaje       TEXT,
    trigger_tipo        VARCHAR(20)     -- 'cron', 'manual', 'webhook'
);

-- =============================================================
-- ÍNDICES — para consultas frecuentes
-- =============================================================
CREATE INDEX IF NOT EXISTS idx_leads_empresa      ON leads(empresa_id);
CREATE INDEX IF NOT EXISTS idx_leads_telefono     ON leads(telefono);
CREATE INDEX IF NOT EXISTS idx_leads_estado       ON leads(estado_gestion);
CREATE INDEX IF NOT EXISTS idx_scores_lead        ON lead_scores(lead_id);
CREATE INDEX IF NOT EXISTS idx_asignaciones_fecha ON lead_asignaciones(fecha_asignacion, asesor_id);
CREATE INDEX IF NOT EXISTS idx_historico_desenlace ON historico_cierres(desenlace, canal);

-- =============================================================
-- ROW LEVEL SECURITY — separación por empresa
-- =============================================================
ALTER TABLE leads              ENABLE ROW LEVEL SECURITY;
ALTER TABLE lead_scores        ENABLE ROW LEVEL SECURITY;
ALTER TABLE lead_asignaciones  ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversaciones     ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversacion_extracciones ENABLE ROW LEVEL SECURITY;

-- Política: cada empresa solo ve sus propios leads
-- El pipeline backend usa service_role (bypasea RLS)
-- El dashboard usa anon key (respeta RLS)
CREATE POLICY leads_por_empresa ON leads
    FOR ALL
    USING (empresa_id = current_setting('app.empresa_id', TRUE));

CREATE POLICY scores_por_empresa ON lead_scores
    FOR ALL
    USING (
        lead_id IN (
            SELECT lead_id FROM leads
            WHERE empresa_id = current_setting('app.empresa_id', TRUE)
        )
    );

CREATE POLICY asignaciones_por_empresa ON lead_asignaciones
    FOR ALL
    USING (
        lead_id IN (
            SELECT lead_id FROM leads
            WHERE empresa_id = current_setting('app.empresa_id', TRUE)
        )
    );

CREATE POLICY conversaciones_por_empresa ON conversaciones
    FOR ALL
    USING (
        lead_id IN (
            SELECT lead_id FROM leads
            WHERE empresa_id = current_setting('app.empresa_id', TRUE)
        )
    );

CREATE POLICY extracciones_por_empresa ON conversacion_extracciones
    FOR ALL
    USING (
        lead_id IN (
            SELECT lead_id FROM leads
            WHERE empresa_id = current_setting('app.empresa_id', TRUE)
        )
    );