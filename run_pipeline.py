# run_pipeline.py
import uuid
import logging
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s — %(levelname)s — %(message)s"
)
logger = logging.getLogger("run_pipeline")

from db.client import get_client
from pipeline.ingest import ingestar_todo
from pipeline.normalize import (
    normalizar_leads,
    normalizar_asesores,
    normalizar_historico,
    persist_historico,
    persist_leads,
    persist_conversaciones
)
from pipeline.deduplicate import deduplicar, persist_duplicates
from pipeline.extract_ai import extraer_conversaciones
from pipeline.score import calcular_scores, persist_scores
from pipeline.assign import asignar_leads, persist_asignaciones


def _verificar_seed() -> None:
    """Falla rápido si los datos maestros no han sido cargados."""
    db = get_client()
    result = db.table("empresas").select("empresa_id").limit(1).execute()
    if not result.data:
        raise RuntimeError(
            "La base de datos no tiene datos maestros. "
            "Ejecuta primero: python -m pipeline.seed"
        )


def _limpiar_run_anterior(db) -> None:
    """
    Elimina scores y asignaciones de runs anteriores antes de iniciar uno nuevo.
    Los leads y conversaciones NO se tocan — solo los datos derivados.
    """
    logger.info("Limpiando scores y asignaciones anteriores...")
    db.table("lead_asignaciones").delete().neq(
        "asignacion_id", "00000000-0000-0000-0000-000000000000"
    ).execute()
    db.table("lead_scores").delete().neq(
        "score_id", "00000000-0000-0000-0000-000000000000"
    ).execute()
    logger.info("✔ Tablas derivadas limpias")


def run(trigger_tipo: str = "manual") -> dict:
    _verificar_seed()

    db = get_client()
    run_id = str(uuid.uuid4())

    logger.info(f"Iniciando pipeline — run_id={run_id} | trigger={trigger_tipo}")

    db.table("pipeline_runs").insert({
        "run_id":       run_id,
        "estado":       "en_proceso",
        "trigger_tipo": trigger_tipo,
        "iniciado_en":  datetime.now(timezone.utc).isoformat(),
    }).execute()

    try:
        # ── Limpieza previa ────────────────────────────────────────────────
        _limpiar_run_anterior(db)   # ← agregar aquí, antes de la etapa 1
        
        # ── 1. Ingesta ─────────────────────────────────────────────────────
        logger.info("── Etapa 1/6: Ingesta")
        datos = ingestar_todo()

        # ── 2. Normalización ───────────────────────────────────────────────
        logger.info("── Etapa 2/6: Normalización")
        leads_norm     = normalizar_leads(datos["leads"], datos["catalogo"])
        asesores_norm  = normalizar_asesores(datos["asesores"])
        historico_norm = normalizar_historico(datos["historico"])

        # persist_conversaciones antes de persist_leads no es posible
        # porque conversaciones.lead_id referencia leads(lead_id)
        persist_leads(leads_norm, run_id)
        persist_conversaciones(datos["conversaciones"])

        historico_norm = normalizar_historico(datos["historico"])
        persist_historico(historico_norm)   

        # ── 3. Deduplicación ───────────────────────────────────────────────
        logger.info("── Etapa 3/6: Deduplicación")
        leads_dedup = deduplicar(leads_norm)
        persist_duplicates(leads_dedup)

        # ── 4. Extracción IA ───────────────────────────────────────────────
        # persist_extraccion se llama internamente por conversación
        logger.info("── Etapa 4/6: Extracción IA")
        extracciones = extraer_conversaciones(
            datos["conversaciones"],
            run_id=run_id,
        )

        # ── 5. Scoring ─────────────────────────────────────────────────────
        logger.info("── Etapa 5/6: Scoring")
        df_scored = calcular_scores(leads_dedup, extracciones)
        persist_scores(df_scored, run_id)

        # ── 6. Asignación ──────────────────────────────────────────────────
        logger.info("── Etapa 6/6: Asignación")
        df_resultado = asignar_leads(df_scored, asesores_norm)
        persist_asignaciones(df_resultado, run_id)

        asignados = int(df_resultado["asignado"].sum())

        # ── Cerrar run exitoso ─────────────────────────────────────────────
        db.table("pipeline_runs").update({
            "estado":           "exitoso",
            "finalizado_en":    datetime.now(timezone.utc).isoformat(),
            "leads_procesados": len(leads_norm),
            "leads_scoring":    len(df_scored),
            "leads_asignados":  asignados,
        }).eq("run_id", run_id).execute()

        logger.info(f"✔ Pipeline completado — {asignados} leads asignados")
        return {"run_id": run_id, "estado": "exitoso", "leads_asignados": asignados}

    except Exception as e:
        logger.error(f"✘ Pipeline fallido: {e}")
        db.table("pipeline_runs").update({
            "estado":        "fallido",
            "finalizado_en": datetime.now(timezone.utc).isoformat(),
            "error_mensaje": str(e),
        }).eq("run_id", run_id).execute()
        raise


if __name__ == "__main__":
    run()