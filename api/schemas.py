from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel


class LeadScore(BaseModel):
    score_id: str
    score_total: Optional[Decimal]
    temperatura: Optional[str]
    score_canal: Optional[Decimal]
    score_tiempo_respuesta: Optional[Decimal]
    score_cuota_inicial: Optional[Decimal]
    score_forma_pago: Optional[Decimal]
    score_intencion: Optional[Decimal]
    score_pidio_cita: Optional[Decimal]
    explicacion: Optional[str]

    class Config:
        from_attributes = True


class LeadAsignacion(BaseModel):
    asignacion_id: str
    asesor_id: str
    fecha_asignacion: str
    orden_prioridad: Optional[int]
    atendido: bool

    class Config:
        from_attributes = True


class LeadResponse(BaseModel):
    # Identidad
    lead_id: str
    empresa_id: str
    punto_venta_id: Optional[str]

    # Contacto
    nombre_cliente: Optional[str]
    telefono: Optional[str]
    email: Optional[str]
    ciudad: Optional[str]

    # Origen
    canal: str
    campania: Optional[str]
    fecha_registro: Optional[datetime]

    # Modelo de interés
    modelo_interes_texto: Optional[str]
    referencia_id: Optional[str]

    # Gestión
    estado_gestion: Optional[str]
    fecha_primer_contacto: Optional[datetime]
    es_duplicado: bool

    # Relaciones embebidas
    score: Optional[LeadScore]
    asignacion: Optional[LeadAsignacion]

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
    email: Optional[str]
    capacidad_diaria: int
    activo: bool

    class Config:
        from_attributes = True


class LeadDeHoyResponse(BaseModel):
    """Lead enriquecido tal como lo ve un asesor en su lista diaria."""
    # Posición en la lista del asesor
    orden_prioridad: Optional[int]
    atendido: bool

    # Datos del lead
    lead_id: str
    nombre_cliente: Optional[str]
    telefono: Optional[str]
    ciudad: Optional[str]
    canal: str
    modelo_interes_texto: Optional[str]
    fecha_registro: Optional[datetime]
    fecha_primer_contacto: Optional[datetime]
    estado_gestion: Optional[str]

    # Score
    score_total: Optional[Decimal]
    temperatura: Optional[str]
    explicacion: Optional[str]

    # Alerta operativa: lleva más de 24h sin contacto
    alerta_sin_contacto: bool

    class Config:
        from_attributes = True


class MisLeadsHoyResponse(BaseModel):
    asesor: AsesorResponse
    fecha: str
    pipeline_run_id: str | None = None
    total_asignados: int
    total_atendidos: int
    leads: list[LeadDeHoyResponse]