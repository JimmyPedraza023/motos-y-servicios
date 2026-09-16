from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from supabase import Client

from api.dependencies import get_db, get_empresa_id
from api.schemas import LeadListResponse, LeadResponse, LeadScore, LeadAsignacion

router = APIRouter(prefix="/leads", tags=["Leads"])


def _build_lead_response(lead: dict, scores: dict, asignaciones: dict) -> LeadResponse:
    """
    Ensambla un LeadResponse combinando el lead con su score y asignación.
    scores y asignaciones son dicts indexados por lead_id.
    """
    lead_id = lead["lead_id"]

    score_data = scores.get(lead_id)
    asignacion_data = asignaciones.get(lead_id)

    return LeadResponse(
        **{k: v for k, v in lead.items() if k not in ("score", "asignacion")},
        score=LeadScore(**score_data) if score_data else None,
        asignacion=LeadAsignacion(**asignacion_data) if asignacion_data else None,
    )


@router.get(
    "",
    response_model=LeadListResponse,
    summary="Lista priorizada de leads",
    description=(
        "Devuelve los leads de la empresa autenticada, ordenados por score descendente. "
        "Excluye duplicados. Permite filtrar por temperatura, canal, ciudad y asesor asignado."
    ),
)
def listar_leads(
    temperatura: Optional[str] = Query(
        None,
        description="Caliente | Tibio | Frio",
        pattern="^(Caliente|Tibio|Frio)$",
    ),
    canal: Optional[str] = Query(
        None,
        description="WhatsApp | Meta Ads | Formulario Web",
    ),
    ciudad: Optional[str] = Query(None, description="Ciudad canónica del lead"),
    asesor_id: Optional[str] = Query(None, description="Filtrar por asesor asignado"),
    sin_contacto_24h: bool = Query(
        False,
        description="Si True, devuelve solo leads sin primer contacto en más de 24 horas",
    ),
    pagina: int = Query(1, ge=1, description="Número de página"),
    por_pagina: int = Query(50, ge=1, le=200, description="Resultados por página"),
    empresa_id: str = Depends(get_empresa_id),
    db: Client = Depends(get_db),
):
    # ── 1. Query base de leads ────────────────────────────────────────────────
    query = (
        db.table("leads")
        .select("*")
        .eq("empresa_id", empresa_id)
        .eq("es_duplicado", False)
    )

    if canal:
        query = query.eq("canal", canal)
    if ciudad:
        query = query.ilike("ciudad", f"%{ciudad}%")
    if sin_contacto_24h:
        from datetime import datetime, timezone, timedelta
        corte = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        query = (
            query
            .is_("fecha_primer_contacto", "null")
            .lt("fecha_registro", corte)
        )

    resultado = query.execute()
    leads = resultado.data or []

    if not leads:
        return LeadListResponse(total=0, pagina=pagina, por_pagina=por_pagina, data=[])

    lead_ids = [l["lead_id"] for l in leads]

    # ── 2. Scores — un fetch por lote ─────────────────────────────────────────
    # Traemos solo el score más reciente por lead usando created_at desc
    scores_raw = (
        db.table("lead_scores")
        .select("*")
        .in_("lead_id", lead_ids)
        .order("created_at", desc=True)
        .execute()
        .data or []
    )
    # Indexamos: primer resultado por lead_id = el más reciente
    scores: dict = {}
    for s in scores_raw:
        if s["lead_id"] not in scores:
            scores[s["lead_id"]] = s

    # ── 3. Filtro por temperatura (post-join) ─────────────────────────────────
    if temperatura:
        lead_ids_temp = {
            lid for lid, s in scores.items() if s.get("temperatura") == temperatura
        }
        leads = [l for l in leads if l["lead_id"] in lead_ids_temp]
        lead_ids = [l["lead_id"] for l in leads]

    # ── 4. Asignaciones de hoy ────────────────────────────────────────────────
    from datetime import date
    hoy = date.today().isoformat()

    asignaciones_query = (
        db.table("lead_asignaciones")
        .select("*")
        .in_("lead_id", lead_ids)
        .eq("fecha_asignacion", hoy)
    )
    if asesor_id:
        asignaciones_query = asignaciones_query.eq("asesor_id", asesor_id)

    asignaciones_raw = asignaciones_query.execute().data or []
    asignaciones: dict = {a["lead_id"]: a for a in asignaciones_raw}

    # Si filtramos por asesor, reducimos leads a los que tienen asignación
    if asesor_id:
        leads = [l for l in leads if l["lead_id"] in asignaciones]
        lead_ids = [l["lead_id"] for l in leads]

    # ── 5. Ordenar por score_total desc ───────────────────────────────────────
    leads.sort(
        key=lambda l: float(scores.get(l["lead_id"], {}).get("score_total") or 0),
        reverse=True,
    )

    # ── 6. Paginación manual ──────────────────────────────────────────────────
    total = len(leads)
    inicio = (pagina - 1) * por_pagina
    fin = inicio + por_pagina
    leads_pagina = leads[inicio:fin]

    # ── 7. Ensamblar respuesta ────────────────────────────────────────────────
    data = [_build_lead_response(l, scores, asignaciones) for l in leads_pagina]

    return LeadListResponse(total=total, pagina=pagina, por_pagina=por_pagina, data=data)


@router.get(
    "/{lead_id}",
    response_model=LeadResponse,
    summary="Detalle de un lead",
)
def obtener_lead(
    lead_id: str,
    empresa_id: str = Depends(get_empresa_id),
    db: Client = Depends(get_db),
):
    # ── Lead ──────────────────────────────────────────────────────────────────
    resultado = (
        db.table("leads")
        .select("*")
        .eq("lead_id", lead_id)
        .eq("empresa_id", empresa_id)   # garantiza separación entre empresas
        .single()
        .execute()
    )

    if not resultado.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead '{lead_id}' no encontrado para esta empresa.",
        )

    lead = resultado.data

    # ── Score más reciente ────────────────────────────────────────────────────
    score_raw = (
        db.table("lead_scores")
        .select("*")
        .eq("lead_id", lead_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
        .data
    )
    score = score_raw[0] if score_raw else None

    # ── Asignación de hoy ─────────────────────────────────────────────────────
    from datetime import date
    asignacion_raw = (
        db.table("lead_asignaciones")
        .select("*")
        .eq("lead_id", lead_id)
        .eq("fecha_asignacion", date.today().isoformat())
        .limit(1)
        .execute()
        .data
    )
    asignacion = asignacion_raw[0] if asignacion_raw else None

    return _build_lead_response(
        lead,
        {lead_id: score} if score else {},
        {lead_id: asignacion} if asignacion else {},
    )