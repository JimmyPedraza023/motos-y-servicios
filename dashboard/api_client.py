import os
import requests
from typing import Optional

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
TIMEOUT = 15  # segundos


def _headers(empresa_id: str) -> dict:
    return {"X-Empresa-ID": empresa_id}


def get_leads(
    empresa_id: str,
    temperatura: Optional[str] = None,
    canal: Optional[str] = None,
    ciudad: Optional[str] = None,
    asesor_id: str | None = None, 
    sin_contacto_24h: bool = False,
    pagina: int = 1,
    por_pagina: int = 200,
) -> dict:
    params = {
        "pagina": pagina,
        "por_pagina": por_pagina,
        "sin_contacto_24h": sin_contacto_24h,
    }
    if temperatura:
        params["temperatura"] = temperatura
    if canal:
        params["canal"] = canal
    if ciudad:
        params["ciudad"] = ciudad
    if asesor_id:                        
        params["asesor_id"] = asesor_id

    r = requests.get(
        f"{API_BASE_URL}/leads",
        params=params,
        headers=_headers(empresa_id),
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def get_lead(empresa_id: str, lead_id: str) -> dict:
    r = requests.get(
        f"{API_BASE_URL}/leads/{lead_id}",
        headers=_headers(empresa_id),
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def get_asesores(empresa_id: str) -> dict:
    r = requests.get(
        f"{API_BASE_URL}/asesores",
        headers=_headers(empresa_id),
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def get_leads_hoy(
    empresa_id: str,
    asesor_id: str,
    solo_pendientes: bool = False,
) -> dict:
    r = requests.get(
        f"{API_BASE_URL}/asesores/{asesor_id}/leads-hoy",
        params={"solo_pendientes": solo_pendientes},
        headers=_headers(empresa_id),
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def marcar_atendido(empresa_id: str, asesor_id: str, lead_id: str) -> dict:
    r = requests.patch(
        f"{API_BASE_URL}/asesores/{asesor_id}/leads-hoy/{lead_id}/atendido",
        headers=_headers(empresa_id),
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def get_pipeline_status() -> dict:
    r = requests.get(f"{API_BASE_URL}/pipeline/status", timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def disparar_pipeline() -> dict:
    r = requests.post(f"{API_BASE_URL}/pipeline/run", timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()