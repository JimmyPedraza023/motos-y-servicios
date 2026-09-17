# Arquitectura — Pipeline de Priorización de Leads con IA

Diagramas del sistema en Mermaid (renderizan nativamente en GitHub).

## 1. Vista general del sistema

```mermaid
flowchart TB
    subgraph SRC["Datos fuente — data/raw/ (sintéticos)"]
        L[leads.csv]
        H[historico_cierres.csv]
        C[catalogo_motos.csv]
        A[asesores.csv]
        J[conversaciones.json]
    end

    subgraph ETL["Pipeline ETL — Python (pipeline/)"]
        ING[ingest] --> NORM[normalize]
        NORM --> DEDUP[deduplicate]
        DEDUP --> AI[extract_ai<br/>NVIDIA NIM · DeepSeek]
        AI --> SCORE[score]
        SCORE --> ASSIGN[assign]
    end

    subgraph DB["Supabase · PostgreSQL + RLS"]
        MD[(Datos maestros<br/>empresas · puntos_venta<br/>catalogo_motos · asesores)]
        RAW[(Leads normalizados<br/>conversaciones · extracciones IA)]
        DER[(Derivados<br/>lead_scores · lead_asignaciones<br/>pipeline_runs)]
    end

    subgraph API["API FastAPI (api/)"]
        R0[health]
        R1[leads]
        R2[asesores]
        R3[pipeline]
    end

    subgraph UI["Dashboard Streamlit (dashboard/)"]
        D1[Vista por empresa X-Empresa-ID]
        D2[Vista asesor · leads de hoy]
    end

    L --> ING
    H -.calibración pesos.-> SCORE
    C --> ING
    A --> ING
    J --> ING

    ETL --> DB

    DB --> API
    API --> UI

    CRON["Scheduler 02:00 COT"] --> ING
    MAN["Comando manual<br/>python run_pipeline.py"] --> ING
    D1 -->|POST /pipeline/run| R3
```

## 2. Escenarios de ejecución del pipeline

```mermaid
sequenceDiagram
    autonumber
    actor U as Usuario
    participant DB as Supabase
    participant RP as run_pipeline.py
    participant ETL as Etapas (ingest→assign)
    participant AI as NVIDIA NIM

    alt Disparo automático (diario)
        Scheduler->>RP: run(trigger_tipo="cron")
    else Disparo manual
        U->>API: POST /pipeline/run
        API->>DB: ¿hay run en_proceso?
        DB-->>API: no
        API->>RP: background task (trigger_tipo="manual")
    end

    RP->>DB: _limpiar_run_anterior (borra scores/asignaciones viejos)
    RP->>RP: _verificar_seed (falla rápido sin datos maestros)
    RP->>ETL: 1) ingestar_todo() → data/raw
    ETL->>ETL: 2) normalizar (E.164, fechas, ciudades, catálogo fuzzy)
    ETL->>ETL: 3) deduplicar (teléfono exacto + fuzzy nombre)
    ETL->>AI: 4) extracción 6 campos por conversación (grupos de 10)
    AI-->>ETL: JSON validado con Pydantic (None si falla)
    ETL->>ETL: 5) calcular_scores (pesos calibrados, suma=100)
    ETL->>ETL: 6) asignar_leads (solo Caliente/Tibio, capacidad por asesor)
    RP->>DB: persist_* (leads → conversaciones → extracciones → scores → asignaciones)
    RP->>DB: pipeline_runs = exitoso
```

> Nota: en `re_score.py` no se borra nada — `persist_scores`/`persist_asignaciones` hacen **upsert** gracias a los índices únicos de las migraciones 002/003.

## 3. Modelo de datos (flujo de dependencias)

```mermaid
flowchart LR
    subgraph Maestros
        E[empresas]
        PV[puntos_venta]
        CAT[catalogo_motos]
        AS[asesores]
    end

    subgraph Operacional
        LD[leads]
        CV[conversaciones]
        EX[conversacion_extracciones]
    end

    subgraph Derivados
        SC[lead_scores]
        ASG[lead_asignaciones]
        PR[pipeline_runs]
    end

    PV --> E
    AS --> PV
    AS --> E
    CAT --> PV
    LD --> E
    LD --> PV
    LD --> CAT
    CV --> LD
    EX --> CV
    SC --> LD
    ASG --> LD
    ASG --> AS
    PR --> SC
    PR --> ASG

    classDef der fill:#fff3cd,stroke:#e0a800
    class SC,ASG,PR der
```

## 4. Separación por empresa (RLS)

```mermaid
flowchart TD
    B[Backend · service_role key] -->|bypasa RLS| DB
    D[Dashboard · anon key] -->|header X-Empresa-ID| API
    API -->|filtros .eq empresa_id en cada query| DB
    DB --> Q["Separación por empresa<br/>en el query del router + políticas RLS<br/>(defensa en profundidad)"]
    Q --> V1["Cada empresa solo ve<br/>sus propios leads/scores/asignaciones"]
```