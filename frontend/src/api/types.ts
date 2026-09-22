export interface LeadScore {
  score_id: string
  score_total: number | null
  temperatura: string | null
  score_canal: number | null
  score_tiempo_respuesta: number | null
  score_cuota_inicial: number | null
  score_forma_pago: number | null
  score_intencion: number | null
  score_pidio_cita: number | null
  explicacion: string | null
}

export interface LeadAsignacion {
  asignacion_id: string
  asesor_id: string
  fecha_asignacion: string
  orden_prioridad: number | null
  atendido: boolean
}

export interface LeadResponse {
  lead_id: string
  empresa_id: string
  punto_venta_id: string | null
  nombre_cliente: string | null
  telefono: string | null
  email: string | null
  ciudad: string | null
  canal: string
  campania: string | null
  fecha_registro: string | null
  modelo_interes_texto: string | null
  referencia_id: string | null
  estado_gestion: string | null
  fecha_primer_contacto: string | null
  es_duplicado: boolean
  score: LeadScore | null
  asignacion: LeadAsignacion | null
}

export interface LeadListResponse {
  total: number
  pagina: number
  por_pagina: number
  data: LeadResponse[]
}

export interface AsesorResponse {
  asesor_id: string
  empresa_id: string
  punto_venta_id: string
  nombre: string
  email: string | null
  capacidad_diaria: number
  activo: boolean
}

export interface AsesoresResponse {
  total: number
  data: AsesorResponse[]
}

export interface LeadDeHoyResponse {
  orden_prioridad: number | null
  atendido: boolean
  lead_id: string
  nombre_cliente: string | null
  telefono: string | null
  ciudad: string | null
  canal: string
  modelo_interes_texto: string | null
  fecha_registro: string | null
  fecha_primer_contacto: string | null
  estado_gestion: string | null
  score_total: number | null
  temperatura: string | null
  explicacion: string | null
  alerta_sin_contacto: boolean
}

export interface MisLeadsHoyResponse {
  asesor: AsesorResponse
  fecha: string
  pipeline_run_id: string | null
  total_asignados: number
  total_atendidos: number
  leads: LeadDeHoyResponse[]
}

export interface PipelineStatus {
  run_id: string
  estado: string
  trigger_tipo: string
  iniciado_en: string
  finalizado_en: string | null
  leads_procesados: number | null
  leads_scoring: number | null
  leads_asignados: number | null
  error_mensaje: string | null
}

export interface MensajeResponse {
  mensaje: string
  run_id?: string | null
}