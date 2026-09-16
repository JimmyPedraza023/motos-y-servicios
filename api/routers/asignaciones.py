# api/routers/asignaciones.py
from datetime import date, datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException, status
from supabase import Client

from api.dependencies import ContextoFecha, get_db, get_empresa_id, get_fecha_gestion
from api.schemas import MisLeadsHoyResponse, AsesorResponse, LeadDeHoyResponse

router = APIRouter(prefix="/asesores", tags=["Asesores"])


def _calcular_alerta(
    fecha_registro_str: Optional[str],
    fecha_primer_contacto_str: Optional[str],
) -> bool:
    if fecha_primer_contacto_str:
        return False
    if not fecha_registro_str:
        return False
    try:
        fecha_registro = datetime.fromisoformat(fecha_registro_str.replace("Z", "+00:00"))
        corte = datetime.now(timezone.utc) - timedelta(hours=24)
        return fecha_registro < corte
    except ValueError:
        return False


def _one_or_none(db_result) -> Optional[dict]:
    """Extrae el primer elemento de una query .limit(1) o devuelve None."""
    data = db_result.data or []
    return data[0] if data else None


@router.get(
    "",
    summary="Lista de asesores",
    description="Devuelve los asesores activos de la empresa autenticada.",
)
def listar_asesores(
    punto_venta_id: Optional[str] = Query(None, description="Filtrar por punto de venta"),
    empresa_id: str = Depends(get_empresa_id),
    db: Client = Depends(get_db),
):
    query = (
        db.table("asesores")
        .select("*")
        .eq("empresa_id", empresa_id)
        .eq("activo", True)
    )
    if punto_venta_id:
        query = query.eq("punto_venta_id", punto_venta_id)

    resultado = query.order("nombre").execute()
    return {
        "total": len(resultado.data or []),
        "data": resultado.data or [],
    }


@router.get(
    "/{asesor_id}/leads-hoy",
    response_model=MisLeadsHoyResponse,
    summary="Mis leads de hoy",
    description=(
        "Lista priorizada de leads asignados a un asesor para el día de hoy. "
        "Incluye score, temperatura y alerta si el lead lleva más de 24h sin contacto."
    ),
)
def leads_de_hoy(
    asesor_id: str,
    solo_pendientes: bool = Query(False, description="Si True, devuelve solo leads no atendidos"),
    empresa_id: str = Depends(get_empresa_id),
    ctx_fecha: ContextoFecha = Depends(get_fecha_gestion),
    db: Client = Depends(get_db),
):
    hoy = ctx_fecha.fecha

    # ── 1. Verificar asesor ───────────────────────────────────────────────────
    asesor = _one_or_none(
        db.table("asesores")
        .select("*")
        .eq("asesor_id", asesor_id)
        .eq("empresa_id", empresa_id)
        .limit(1)
        .execute()
    )
    if not asesor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asesor '{asesor_id}' no encontrado para la empresa '{empresa_id}'.",
        )

    # ── 2. TODAS las asignaciones de la fecha (sin filtrar por atendido) ──────
    # Se traen completas para poder calcular totales reales, independientemente
    # de si luego se filtra la lista mostrada con solo_pendientes.
    todas_asignaciones = (
        db.table("lead_asignaciones")
        .select("*")
        .eq("asesor_id", asesor_id)
        .eq("fecha_asignacion", hoy)
        .order("orden_prioridad")
        .execute()
        .data or []
    )

    total_asignados = len(todas_asignaciones)
    total_atendidos = sum(1 for a in todas_asignaciones if a.get("atendido"))

    # ── 3. Lista a mostrar: el filtro solo_pendientes se aplica aquí ──────────
    asignaciones_raw = (
        [a for a in todas_asignaciones if not a.get("atendido")]
        if solo_pendientes
        else todas_asignaciones
    )

    if not asignaciones_raw:
        return MisLeadsHoyResponse(
            asesor=AsesorResponse(**asesor),
            fecha=hoy,
            pipeline_run_id=ctx_fecha.pipeline_run_id,
            total_asignados=total_asignados,
            total_atendidos=total_atendidos,
            leads=[],
        )

    lead_ids = [a["lead_id"] for a in asignaciones_raw]

    # ── 4. Leads ──────────────────────────────────────────────────────────────
    leads_raw = (
        db.table("leads")
        .select(
            "lead_id, nombre_cliente, telefono, ciudad, canal, "
            "modelo_interes_texto, fecha_registro, fecha_primer_contacto, "
            "estado_gestion, empresa_id"
        )
        .in_("lead_id", lead_ids)
        .eq("empresa_id", empresa_id)
        .execute()
        .data or []
    )
    leads_por_id = {l["lead_id"]: l for l in leads_raw}

    # ── 5. Scores más recientes ───────────────────────────────────────────────
    scores_raw = (
        db.table("lead_scores")
        .select("lead_id, score_total, temperatura, explicacion, created_at")
        .in_("lead_id", lead_ids)
        .order("created_at", desc=True)
        .execute()
        .data or []
    )
    scores_por_lead: dict = {}
    for s in scores_raw:
        if s["lead_id"] not in scores_por_lead:
            scores_por_lead[s["lead_id"]] = s

    # ── 6. Ensamblar ──────────────────────────────────────────────────────────
    leads_respuesta: list[LeadDeHoyResponse] = []
    for asig in asignaciones_raw:
        lid = asig["lead_id"]
        lead = leads_por_id.get(lid, {})
        score = scores_por_lead.get(lid, {})

        leads_respuesta.append(
            LeadDeHoyResponse(
                orden_prioridad=asig.get("orden_prioridad"),
                atendido=asig.get("atendido", False),
                lead_id=lid,
                nombre_cliente=lead.get("nombre_cliente"),
                telefono=lead.get("telefono"),
                ciudad=lead.get("ciudad"),
                canal=lead.get("canal", ""),
                modelo_interes_texto=lead.get("modelo_interes_texto"),
                fecha_registro=lead.get("fecha_registro"),
                fecha_primer_contacto=lead.get("fecha_primer_contacto"),
                estado_gestion=lead.get("estado_gestion"),
                score_total=score.get("score_total"),
                temperatura=score.get("temperatura"),
                explicacion=score.get("explicacion"),
                alerta_sin_contacto=_calcular_alerta(
                    lead.get("fecha_registro"),
                    lead.get("fecha_primer_contacto"),
                ),
            )
        )

    return MisLeadsHoyResponse(
        asesor=AsesorResponse(**asesor),
        fecha=hoy,
        pipeline_run_id=ctx_fecha.pipeline_run_id,
        total_asignados=total_asignados,
        total_atendidos=total_atendidos,
        leads=leads_respuesta,
    )


@router.patch(
    "/{asesor_id}/leads-hoy/{lead_id}/atendido",
    summary="Marcar lead como atendido",
    description="Marca un lead de la lista de hoy como atendido por el asesor.",
)
def marcar_atendido(
    asesor_id: str,
    lead_id: str,
    empresa_id: str = Depends(get_empresa_id),
    ctx_fecha: ContextoFecha = Depends(get_fecha_gestion),    
    db: Client = Depends(get_db),
):
    hoy = ctx_fecha.fecha   

    # ── Verificar que el asesor pertenece a la empresa ────────────────────────
    asesor_check = _one_or_none(
        db.table("asesores")
        .select("asesor_id")
        .eq("asesor_id", asesor_id)
        .eq("empresa_id", empresa_id)
        .limit(1)
        .execute()
    )
    if not asesor_check:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asesor '{asesor_id}' no encontrado para la empresa '{empresa_id}'.",
        )

    # ── Verificar asignación ──────────────────────────────────────────────────
    asig = _one_or_none(
        db.table("lead_asignaciones")
        .select("asignacion_id, atendido")
        .eq("asesor_id", asesor_id)
        .eq("lead_id", lead_id)
        .eq("fecha_asignacion", hoy)
        .limit(1)
        .execute()
    )
    if not asig:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No hay asignación activa para el lead '{lead_id}' y asesor '{asesor_id}' en la fecha '{hoy}'.",
        )

    # ── Verificar que el lead pertenece a la empresa ──────────────────────────
    lead_check = _one_or_none(
        db.table("leads")
        .select("lead_id")
        .eq("lead_id", lead_id)
        .eq("empresa_id", empresa_id)
        .limit(1)
        .execute()
    )
    if not lead_check:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El lead no pertenece a esta empresa.",
        )

    db.table("lead_asignaciones").update({"atendido": True}).eq(
        "asignacion_id", asig["asignacion_id"]
    ).execute()

    return {"mensaje": "Lead marcado como atendido.", "lead_id": lead_id}