# api/main.py
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import health, leads, asignaciones, pipeline   
from api.scheduler import iniciar_scheduler, detener_scheduler   


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s — %(levelname)s — %(message)s",
)
logger = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Arranque ──────────────────────────────────────────────────────────
    from db.client import get_client
    try:
        get_client()
        logger.info("✔ Conexión a Supabase establecida")
    except Exception as e:
        logger.error(f"✘ No se pudo conectar a Supabase: {e}")

    iniciar_scheduler()  # ← inicia el cron nocturno

    yield

    # ── Apagado ───────────────────────────────────────────────────────────
    detener_scheduler()  # ← apaga limpiamente el scheduler
    logger.info("API detenida")


app = FastAPI(
    title="Motos y Servicios — API de Priorización de Leads",
    description=(
        "Pipeline de IA que convierte leads crudos en listas priorizadas "
        "de gestión diaria por asesor. Separación estricta por empresa."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(leads.router)
app.include_router(asignaciones.router)
app.include_router(pipeline.router)  # ← nuevo


@app.get("/", include_in_schema=False)
def root():
    return {"mensaje": "API operando. Documentación en /docs"}