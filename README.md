# Pipeline de Priorización de Leads con IA

Solución técnica para el assessment de **Analista de IA — Motos y Servicios de Colombia S.A.S.** (Gerencia de IA y Transformación).

Convierte los leads crudos de un CRM compartido (WhatsApp, Meta Ads y Formulario Web) en una **lista priorizada de gestión diaria por asesor**, enriquecida con la información que hoy está enterrada en las conversaciones de WhatsApp y respetando la **separación estricta por empresa**.

## Qué hace

1. **Ingesta sin intervención manual** — lee `data/raw/*.csv|json` (datos sintéticos del enunciado). Los leads que ya existen en la base de datos no se sobrescriben con la re-ingesta: el archivo fuente solo crea leads nuevos, nunca revierte el estado de gestión de uno que ya está en operación (ver [Decisiones técnicas](#decisiones-técnicas)).
2. **Normalización** — teléfono a E.164, fechas a ISO 8601, ciudades a valor canónico, canales a 3 valores, modelo de interés mapeado al catálogo con fuzzy matching.
3. **Deduplicación** — la misma persona por dos canales se detecta por teléfono normalizado (exacto) y por nombre (fuzzy, umbral 88) dentro de la misma empresa.
4. **Extracción con IA** — NVIDIA NIM (DeepSeek) estructura cada conversación de WhatsApp en 6 campos: modelo de interés, presupuesto/cuota, forma de pago, intención declarada, objeción principal y si pidió cita/cotización.
5. **Scoring explicable** — cada lead recibe un score 0–100 y una temperatura (`Caliente | Tibio | Frio`), calibrado con las tasas de cierre reales de `historico_cierres.csv`. Se recalcula en cada corrida porque el componente temporal (`score_tiempo_respuesta`) depende de cuánto tiempo lleva el lead sin contacto.
6. **Asignación diaria** — solo los leads `Caliente`/`Tibio` se asignan a asesores respetando capacidad diaria y punto de venta; los `Frio` quedan en cola. La asignación es **idempotente respecto al estado operativo**: un lead ya atendido (`atendido = true`) nunca vuelve a entrar al pool de reasignación ni pierde su asesor o su estado al correr el pipeline de nuevo.
7. **Publicación** — API FastAPI + tablero Streamlit con la vista "mis leads de hoy" por asesor y filtro por empresa.

## Arquitectura

```
data/raw (fuentes) ─► pipeline/ (ETL + IA) ─► Supabase (PostgreSQL + RLS) ─► API FastAPI ─► dashboard Streamlit
                                       ▲
                              scheduler nocturno (02:00 COT) · disparo API · comando manual
```

Diagrama completo en [docs/arquitectura.md](docs/arquitectura.md).

- `pipeline/` — etapas ETL puras (`ingest`, `normalize`, `deduplicate`, `extract_ai`, `score`, `assign`, `seed`). Cada etapa expone su `persist_*` hacia Supabase.
- `api/` — FastAPI con routers `health`, `leads`, `asesores` y `pipeline`. Swagger en `/docs`.
- `db/` — cliente Supabase (`db/client.py`), `schema.sql` con RLS y migraciones en `db/migrations/`.
- `dashboard/` — Streamlit que consume la API vía `requests`.
- Root — orquestadores: `run_pipeline.py` (pipeline completo) y `re_score.py` (re-scoring sin IA).

## Requisitos

- Python 3.12
- Cuenta de [Supabase](https://supabase.com) (PostgreSQL con RLS)
- API key de [NVIDIA NIM](https://integrate.api.nvidia.com) (OpenAI-compatible)
- Repositorio con el venv creado: `.venv\Scripts\python.exe`

## Configuración

1. Clonar el repo y crear el entorno:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

2. Copiar `.env.example` a `.env` y completar:

```env
AI_API_KEY=        # clave NVIDIA NIM (requerida para extracción IA)
AI_MODEL=deepseek-ai/deepseek-v4-flash-0731
AI_BASE_URL=https://integrate.api.nvidia.com/v1
AI_MAX_TOKENS=512

SUPABASE_URL=
SUPABASE_ANON_KEY=           # la usa el dashboard a través de la API
SUPABASE_SERVICE_ROLE_KEY=   # la usa el backend (bypasa RLS)
```

3. Aplicar el esquema: ejecutar `db/schema.sql` y las migraciones `db/migrations/*.sql`, en orden, en el SQL Editor de Supabase (incluye `006_change_lead_asignaciones_unique_constraint.sql`, que habilita la idempotencia de asignaciones — ver [Decisiones técnicas](#decisiones-técnicas)).

## Ejecución

> Todos los comandos se ejecutan desde la raíz del repo con el intérprete del venv.

| Comando | Descripción |
| --- | --- |
| `python -m pipeline.seed` | Carga datos maestros (empresas → puntos_venta → catalogo_motos → asesores). **Obligatorio una vez antes de cualquier run.** |
| `python run_pipeline.py` | Ejecuta el pipeline completo de punta a punta (un solo disparo). |
| `python re_score.py` | Recalcula scoring y asignación sin volver a llamar a la IA (upsert, no borra). |
| `python -m pipeline.extract_ai` | Solo extracción IA (modo prueba con `limite=5`). Consume tokens. |
| `.venv\Scripts\uvicorn.exe api.main:app --reload` | Levanta la API (Swagger en `/docs`). Arranca el scheduler nocturno. |
| `.venv\Scripts\streamlit.exe run dashboard\app.py` | Levanta el tablero (requiere la API en `localhost:8000`). |

### Flujo típico

```powershell
python -m pipeline.seed                       # 1. una sola vez
python run_pipeline.py                        # 2. pipeline completo
# o expone la API:
.venv\Scripts\uvicorn.exe api.main:app --reload
.venv\Scripts\streamlit.exe run dashboard\app.py    # POST /pipeline/run
```

## API

La autenticación por empresa es por header `X-Empresa-ID` (`EMP-01`, `EMP-02`, `EMP-03`), validado contra la tabla `empresas`.

| Método | Ruta | Descripción |
| --- | --- | --- |
| GET | `/health` | Health check + estado de la conexión a Supabase |
| GET | `/leads` | Leads de la empresa, ordenados por score desc, con filtros (temperatura, canal, ciudad, asesor, sin contacto >24h) y paginación |
| GET | `/leads/{lead_id}` | Detalle de un lead con su score y asignación del día |
| GET | `/asesores` | Asesores activos de la empresa |
| GET | `/asesores/{asesor_id}/leads-hoy` | "Mis leads de hoy": lista priorizada del asesor con score, temperatura y alerta de +24h sin contacto |
| PATCH | `/asesores/{asesor_id}/leads-hoy/{lead_id}/atendido` | Marcar lead como atendido |
| POST | `/pipeline/run` | Dispara el pipeline completo en background (409 si hay un run `en_proceso`) |
| GET | `/pipeline/status` | Estado del último run |

## Decisiones técnicas

- **Supabase + RLS** para cumplir la separación por empresa: el backend usa `service_role` (bypasa RLS); el dashboard usa la `anon key` a través de la API, que valida `X-Empresa-ID`. Las políticas por empresa se definen en `db/schema.sql`.
- **Scoring por reglas calibradas, no con un modelo entrenado:** se calcularon las tasas de cierre reales por canal, cuota declarada, forma de pago, cita solicitada y ventana de contacto desde `historico_cierres.csv`, y se usaron como pesos (que suman 100, verificado con un `assert` en `pipeline/score.py`). Resultado explicable y defendible ante negocio.
- **Deduplicación en dos pasos** (teléfono exacto + fuzzy por nombre): el primer paso atrapa el caso real de una persona escribiendo por dos canales; el segundo cubre leads sin teléfono. Solo se asigna el lead canónico.
- **Extracción IA tolerante a fallos:** validación Pydantic de la respuesta, reintentos con backoff (429/504/529), checkpoint en `data/processed/extracciones.json` para reanudar runs interrumpidos, y campos `None` (nunca defaults falsos) ante fallo para no contaminar el scoring.
- **Idempotencia del estado operativo de asignación** (el punto más delicado del diseño): el pipeline distingue entre datos *recalculables* y *estado con memoria*:
  - `lead_scores` se limpia y recalcula por completo en cada corrida — no guarda estado operativo, y el score debe reflejar siempre la información más reciente (ej. horas transcurridas sin contacto).
  - `lead_asignaciones` **no se borra**. `persist_asignaciones` hace `upsert` con `on_conflict="lead_id"` (una fila viva por lead, no una por corrida), y nunca sobrescribe la columna `atendido`. Antes de asignar, `run_pipeline.py` consulta qué leads ya tienen `atendido = true` y los excluye del pool de elegibles en `pipeline/assign.py`, además de descontar esa cantidad de la capacidad diaria disponible de cada asesor para no sobre-asignarlo.
  - `persist_leads` usa `upsert(..., ignore_duplicates=True)`: un lead nuevo en el archivo fuente se inserta, pero uno que ya existe en base de datos no se toca — así la re-ingesta del CSV estático nunca revierte `estado_gestion` ni `fecha_primer_contacto` que ya fueron actualizados desde el dashboard/API.
  - La migración `006_change_lead_asignaciones_unique_constraint.sql` mueve la unique constraint de `(lead_id, pipeline_run_id)` a `lead_id`, que es lo que habilita el `upsert` idempotente por lead.
  - `re_score.py` ya seguía este mismo principio (upsert, no borra, conserva `atendido`); el cambio alinea `run_pipeline.py` con ese mismo comportamiento.
- **Orquestación de punta a punta:** el pipeline corre con un solo comando, se dispara desde la API en background (con bloqueo de concurrencia) y el scheduler de la API lo corre automáticamente a las 02:00 (hora Colombia).

## Supuestos asumidos

- Los datos de `data/raw/` son sintéticos e incluyen inconsistencias deliberadas (ver `data/raw/LEEME.txt`). No se corrigieron los datos de origen silenciosamente; `pipeline/ingest.py` maneja los conocidos (p. ej. `lead_id` duplicados por error del CRM) y los demás quedan tipados como `None` en la normalización.
- El grupo se modela con **tres empresas** (`EMP-01` a `EMP-03`) derivadas de los datos de entrada.
- Solo los leads `Caliente` y `Tibio` consumen capacidad de los asesores; los `Frio` quedan sin asignar.
- La ventana de contacto crítico es de **24 horas**: pasado ese plazo sin `fecha_primer_contacto`, el lead se marca con alerta en el tablero.
- Un lead se considera "en operación" una vez existe en base de datos: los archivos fuente estáticos solo alimentan altas nuevas, nunca sobrescriben el estado de gestión de un lead que el equipo comercial ya está trabajando.
- El tamaño de los datos es relativamente pequeño (≈1.500 leads, 677 conversaciones), así que el pipeline se ejecuta en una sola pasada en memoria (pandas) sin Spark ni bases vectoriales; la pendiente se escala con particionado.

## Publicación

- **API + dashboard:** desplegados como dos servicios independientes (Render para la API, Streamlit Cloud para el dashboard).
- **URL pública:** https://motos-y-servicios.streamlit.app/
- **Scheduler:** el servicio API incluye el cron nocturno (02:00 Colombia), por lo que no se necesita un cron externo; al desplegarse con una sola instancia, el scheduler queda en esa instancia y con `--reload` desactivado.

## Trabajo futuro

- **Con más tiempo haría:**
  - **Asignación "pegajosa" también para leads pendientes:** hoy la idempotencia protege a los leads con `atendido = true`, pero un lead asignado y aún no atendido vuelve a pasar por el algoritmo de asignación en cada corrida y, en teoría, podría cambiar de asesor si varía el orden de score o la capacidad disponible. La extensión natural es fijar también la asignación de todo lead con `asignado = true`, sin importar si ya fue atendido, y solo liberarlo explícitamente por reglas de negocio (ej. reasignar si pasan más de 24h sin contacto).
  - Suite de validación: medir el lift del scoring contra `historico_cierres.csv` (KS/AUC) y añadir un notebook de calibración que regenere los pesos desde datos en vez de tenerlos como constantes comentadas.
  - Procesamiento de conversaciones en streaming y encolado real (Celery/Redis) en lugar del hilo en background de FastAPI.
  - Almacenar `raw_response` (ya persiste) y montar un labeler humano para futuros fine-tunes / prompt tuning.
  - Tests automatizados (pytest) y CI (lint + typecheck + tests en GitHub Actions), incluyendo un test de regresión específico para el escenario de idempotencia (marcar atendido → rerun → verificar que no cambia).
  - Autenticación real de asesores (login) en el dashboard y auditoría de cambios.
  - Reentrenamiento del prompt de extracción con ejemplos colombianos y validación por pares.