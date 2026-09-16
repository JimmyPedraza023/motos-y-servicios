from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from supabase import Client
from api.dependencies import get_db

router = APIRouter(prefix="/health", tags=["Sistema"])


@router.get(
    "",
    summary="Health check",
    description="Verifica que la API y la conexión a Supabase estén operando.",
)
def health_check(db: Client = Depends(get_db)):
    """
    Devuelve OK si la API responde y puede hacer al menos una consulta a Supabase.
    Útil para el health check de Railway / Render.
    """
    try:
        db.table("empresas").select("empresa_id").limit(1).execute()
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {e}"

    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": db_status,
    }