# re_score.py — script puntual, no reemplaza run_pipeline.py
import uuid
import logging
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(levelname)s — %(message)s")
logger = logging.getLogger("re_score")

from db.client import get_client
from pipeline.ingest import ingestar_todo
from pipeline.normalize import normalizar_leads, normalizar_asesores
from pipeline.deduplicate import deduplicar
from pipeline.score import calcular_scores, persist_scores
from pipeline.assign import asignar_leads, persist_asignaciones


def re_score():
    db = get_client()

    # Reutilizar el run_id del último run exitoso para mantener trazabilidad
    ultimo_run = (
        db.table("pipeline_runs")
        .select("run_id")
        .eq("estado", "exitoso")
        .order("finalizado_en", desc=True)
        .limit(1)
        .execute()
    )
    run_id = ultimo_run.data[0]["run_id"] if ultimo_run.data else str(uuid.uuid4())
    logger.info(f"Re-scoring sobre run_id={run_id}")

    # Reconstruir DataFrames desde los archivos originales
    datos = ingestar_todo()
    leads_norm = normalizar_leads(datos["leads"], datos["catalogo"])
    asesores_norm = normalizar_asesores(datos["asesores"])
    leads_dedup = deduplicar(leads_norm)

    # Leer extracciones ya persistidas en BD (no vuelve a llamar a la API de IA)
    logger.info("Leyendo extracciones desde BD...")
    ext_raw = (
        db.table("conversacion_extracciones")
        .select("*")
        .execute()
        .data or []
    )

    # Adaptar al formato que espera calcular_scores
    extracciones = [
        {
            "lead_id":              e.get("lead_id"),
            "extraccion_exitosa":   True,
            "modelo_interes":       e.get("modelo_interes"),
            "presupuesto_cuota":    e.get("presupuesto_cuota"),
            "forma_pago":           e.get("forma_pago"),
            "intencion_declarada":  e.get("intencion_declarada"),
            "objecion_principal":   e.get("objecion_principal"),
            "pidio_cita_cotizacion": e.get("pidio_cita_cotizacion"),
        }
        for e in ext_raw
    ]

    # Limpiar scores y asignaciones anteriores antes de re-persistir
    logger.info("Limpiando lead_scores y lead_asignaciones anteriores...")
    db.table("lead_scores").delete().neq("score_id", "00000000-0000-0000-0000-000000000000").execute()
    db.table("lead_asignaciones").delete().neq("asignacion_id", "00000000-0000-0000-0000-000000000000").execute()

    # Re-calcular y persistir
    logger.info("Calculando scores...")
    df_scored = calcular_scores(leads_dedup, extracciones)
    persist_scores(df_scored, run_id)

    logger.info("Asignando leads...")
    df_resultado = asignar_leads(df_scored, asesores_norm)
    persist_asignaciones(df_resultado, run_id)

    asignados = int(df_resultado["asignado"].sum())
    logger.info(f"✔ Re-scoring completado — {asignados} leads asignados")


if __name__ == "__main__":
    re_score()