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

    run_id = str(uuid.uuid4())   # run propio, no reutilizar uno viejo
    trigger_registrado_en = datetime.now(timezone.utc).isoformat()

    db.table("pipeline_runs").insert({
        "run_id": run_id,
        "estado": "en_proceso",
        "trigger_tipo": "manual_rescore",
        "iniciado_en": trigger_registrado_en,
    }).execute()

    logger.info(f"Re-scoring — run_id={run_id}")

    datos = ingestar_todo()
    leads_norm = normalizar_leads(datos["leads"], datos["catalogo"])
    asesores_norm = normalizar_asesores(datos["asesores"])
    leads_dedup = deduplicar(leads_norm)

    logger.info("Leyendo extracciones desde BD...")
    ext_raw = db.table("conversacion_extracciones").select("*").execute().data or []
    extracciones = [
        {
            "lead_id":               e.get("lead_id"),
            "extraccion_exitosa":    True,
            "modelo_interes":        e.get("modelo_interes"),
            "presupuesto_cuota":     e.get("presupuesto_cuota"),
            "forma_pago":            e.get("forma_pago"),
            "intencion_declarada":   e.get("intencion_declarada"),
            "objecion_principal":    e.get("objecion_principal"),
            "pidio_cita_cotizacion": e.get("pidio_cita_cotizacion"),
        }
        for e in ext_raw
    ]

    # SIN deletes — persist_scores y persist_asignaciones deben hacer upsert
    logger.info("Calculando scores...")
    df_scored = calcular_scores(leads_dedup, extracciones)
    persist_scores(df_scored, run_id)          # upsert por lead_id

    logger.info("Asignando leads...")
    df_resultado = asignar_leads(df_scored, asesores_norm)
    persist_asignaciones(df_resultado, run_id)  # upsert por (lead_id, fecha_asignacion), sin resetear "atendido"

    asignados = int(df_resultado["asignado"].sum())

    db.table("pipeline_runs").update({
        "estado": "exitoso",
        "finalizado_en": datetime.now(timezone.utc).isoformat(),
        "leads_asignados": asignados,
    }).eq("run_id", run_id).execute()

    logger.info(f"✔ Re-scoring completado — {asignados} leads asignados")

if __name__ == "__main__":
    re_score()