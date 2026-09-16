import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from db.client import get_client

logger = logging.getLogger("api.pipeline")
router = APIRouter(prefix="/pipeline", tags=["Pipeline"])


class PipelineRunResponse(BaseModel):
    mensaje: str
    run_id: str | None = None


def _ejecutar_pipeline(trigger_tipo: str) -> None:
    """
    Función que corre en background. Importa run() aquí (no al top-level)
    para evitar que el worker importe todo el pipeline al arrancar la API.
    """
    try:
        from run_pipeline import run
        run(trigger_tipo=trigger_tipo)
    except Exception as e:
        logger.error(f"Pipeline fallido en background: {e}")


@router.post(
    "/run",
    response_model=PipelineRunResponse,
    summary="Dispara el pipeline manualmente",
    description=(
        "Encola una ejecución completa del pipeline (ingesta → scoring → asignación) "
        "en segundo plano. Retorna inmediatamente con un mensaje de confirmación. "
        "El estado del run se puede consultar en la tabla `pipeline_runs`."
    ),
)
def disparar_pipeline(background_tasks: BackgroundTasks) -> PipelineRunResponse:
    # Verificar que no haya un run en curso antes de encolar otro
    db = get_client()
    result = (
        db.table("pipeline_runs")
        .select("run_id, estado")
        .eq("estado", "en_proceso")
        .limit(1)
        .execute()
    )
    if result.data:
        run_id_activo = result.data[0]["run_id"]
        raise HTTPException(
            status_code=409,
            detail=f"Ya hay un pipeline en curso (run_id={run_id_activo}). Espera a que finalice.",
        )

    background_tasks.add_task(_ejecutar_pipeline, "manual")
    logger.info("Pipeline encolado vía POST /pipeline/run")

    return PipelineRunResponse(
        mensaje="Pipeline encolado. Consulta /pipeline/status para el resultado.",
    )


@router.get(
    "/status",
    summary="Estado del último pipeline run",
)
def estado_pipeline():
    """Devuelve el run más reciente con su estado, contadores y posible error."""
    db = get_client()
    result = (
        db.table("pipeline_runs")
        .select(
            "run_id, estado, trigger_tipo, iniciado_en, "
            "finalizado_en, leads_procesados, leads_scoring, "
            "leads_asignados, error_mensaje"
        )
        .order("iniciado_en", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="No hay runs registrados aún.")
    return result.data[0]