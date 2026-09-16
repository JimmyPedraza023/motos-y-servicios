from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator


# ── Validador reutilizable ────────────────────────────────────────────────────
def _to_float(v):
    """Convierte string o Decimal a float. Acepta None."""
    if v is None:
        return None
    return float(v)


class LeadScore(BaseModel):
    score_id: str
    score_total: Optional[float] = None
    temperatura: Optional[str] = None
    score_canal: Optional[float] = None
    score_tiempo_respuesta: Optional[float] = None
    score_cuota_inicial: Optional[float] = None
    score_forma_pago: Optional[float] = None
    score_intencion: Optional[float] = None
    score_pidio_cita: Optional[float] = None
    explicacion: Optional[str] = None

    @field_validator(
        "score_total", "score_canal", "score_tiempo_respuesta",
        "score_cuota_inicial", "score_forma_pago", "score_intencion",
        "score_pidio_cita",
        mode="before",
    )
    @classmethod
    def parsear_numeric(cls, v):
        return _to_float(v)

    class Config:
        from_attributes = True


class LeadAsignacion(BaseModel):
    asignacion_id: str
    asesor_id: str
    fecha_asignacion: str
    orden_prioridad: Optional[int] = None
    atendido: bool

    class Config:
        from_attributes = True


class LeadResponse(BaseModel):
    # Identidad
    lead_id: str
    empresa_id: str
    punto_venta_id: Optional[str] = None

    # Contacto
    nombre_cliente: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    ciudad: Optional[str] = None

    # Origen
    canal: str
    campania: Optional[str] = None
    fecha_registro: Optional[datetime] = None

    # Modelo de interés
    modelo_interes_texto: Optional[str] = None
    referencia_id: Optional[str] = None

    # Gestión
    estado_gestion: Optional[str] = None
    fecha_primer_contacto: Optional[datetime] = None
    es_duplicado: bool

    # Relaciones embebidas
    score: Optional[LeadScore] = None
    asignacion: Optional[LeadAsignacion] = None

    class Config:
        from_attributes = True


class LeadListResponse(BaseModel):
    total: int
    pagina: int
    por_pagina: int
    data: list[LeadResponse]


class AsesorResponse(BaseModel):
    asesor_id: str
    empresa_id: str
    punto_venta_id: str
    nombre: str
    email: Optional[str] = None
    capacidad_diaria: int
    activo: bool

    class Config:
        from_attributes = True


class LeadDeHoyResponse(BaseModel):
    """Lead enriquecido tal como lo ve un asesor en su lista diaria."""
    # Posición en la lista del asesor
    orden_prioridad: Optional[int] = None
    atendido: bool

    # Datos del lead
    lead_id: str
    nombre_cliente: Optional[str] = None
    telefono: Optional[str] = None
    ciudad: Optional[str] = None
    canal: str
    modelo_interes_texto: Optional[str] = None
    fecha_registro: Optional[datetime] = None
    fecha_primer_contacto: Optional[datetime] = None
    estado_gestion: Optional[str] = None

    # Score
    score_total: Optional[float] = None
    temperatura: Optional[str] = None
    explicacion: Optional[str] = None

    # Alerta operativa
    alerta_sin_contacto: bool

    @field_validator("score_total", mode="before")
    @classmethod
    def parsear_score(cls, v):
        return _to_float(v)

    class Config:
        from_attributes = True


class MisLeadsHoyResponse(BaseModel):
    asesor: AsesorResponse
    fecha: str
    pipeline_run_id: str | None = None
    total_asignados: int
    total_atendidos: int
    leads: list[LeadDeHoyResponse]