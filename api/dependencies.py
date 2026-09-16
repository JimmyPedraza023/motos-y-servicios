# api/dependencies.py
from fastapi import Header, HTTPException, status, Query, Depends
from supabase import Client
from pydantic import BaseModel
from db.client import get_client
from datetime import date

# Cache en memoria — se llena en el primer request y no vuelve a consultar
_empresas_cache: set[str] = set()


def _get_empresas_validas(db: Client) -> set[str]:
    global _empresas_cache
    if not _empresas_cache:
        resultado = db.table("empresas").select("empresa_id").eq("activa", True).execute()
        _empresas_cache = {row["empresa_id"] for row in (resultado.data or [])}
    return _empresas_cache


def get_db() -> Client:
    return get_client()


def get_empresa_id(
    x_empresa_id: str = Header(
        ...,
        description="ID de la comercializadora. Ejemplo: EMP-01",
        alias="X-Empresa-ID",
    )
) -> str:
    db = get_client()
    empresas_validas = _get_empresas_validas(db)

    if x_empresa_id not in empresas_validas:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Empresa '{x_empresa_id}' no reconocida o sin acceso.",
        )
    return x_empresa_id


class ContextoFecha(BaseModel):
    fecha: str
    pipeline_run_id: str | None = None
    fuente: str  # "manual" | "ultimo_run" | "hoy_real"


def _fecha_ultimo_run_exitoso(db: Client) -> ContextoFecha:
    """
    Busca el último pipeline_run con estado 'exitoso' y devuelve
    la fecha_asignacion asociada a ese run. Si no hay runs exitosos
    registrados, o el run no generó asignaciones, cae de vuelta
    a la fecha real del sistema.
    """
    run = (
        db.table("pipeline_runs")
        .select("run_id, finalizado_en")
        .eq("estado", "exitoso")
        .order("finalizado_en", desc=True)
        .limit(1)
        .execute()
        .data
    )
    if not run:
        return ContextoFecha(fecha=date.today().isoformat(), fuente="hoy_real")

    run_id = run[0]["run_id"]

    asignacion = (
        db.table("lead_asignaciones")
        .select("fecha_asignacion")
        .eq("pipeline_run_id", run_id)
        .limit(1)
        .execute()
        .data
    )
    if not asignacion:
        return ContextoFecha(fecha=date.today().isoformat(), pipeline_run_id=run_id, fuente="hoy_real")

    return ContextoFecha(
        fecha=asignacion[0]["fecha_asignacion"],
        pipeline_run_id=run_id,
        fuente="ultimo_run",
    )


def get_fecha_gestion(
    fecha: str | None = Query(
        None,
        description="Fecha a consultar (YYYY-MM-DD). Si se omite, usa la fecha del último pipeline_run exitoso.",
    ),
    db: Client = Depends(get_db),
) -> ContextoFecha:
    if fecha:
        return ContextoFecha(fecha=fecha, fuente="manual")
    return _fecha_ultimo_run_exitoso(db)