import type {
  AsesoresResponse,
  LeadListResponse,
  MensajeResponse,
  MisLeadsHoyResponse,
  PipelineStatus,
} from './types'

export const API_BASE: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '/api'

const TIMEOUT_MS = 15000

interface RequestOptions {
  method?: string
  query?: Record<string, string | number | boolean | null | undefined>
  headers?: Record<string, string>
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const clean = path.startsWith('/') ? path : `/${path}`
  const url = new URL(`${API_BASE}${clean}`, window.location.origin)
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== '') {
        url.searchParams.set(key, String(value))
      }
    }
  }
  return url.toString()
}

export async function request<T>(
  path: string,
  options: RequestOptions = {},
  empresaId?: string,
): Promise<T> {
  const headers: Record<string, string> = { ...options.headers }
  if (empresaId) headers['X-Empresa-ID'] = empresaId

  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), TIMEOUT_MS)

  let res: Response
  try {
    res = await fetch(buildUrl(path, options.query), {
      method: options.method ?? 'GET',
      headers,
      signal: controller.signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('La petición tardó demasiado.')
    }
    throw new Error('No se pudo conectar con la API.')
  } finally {
    window.clearTimeout(timer)
  }

  if (!res.ok) {
    let detail = `Error HTTP ${res.status}`
    try {
      const body = await res.json()
      if (body && typeof body.detail === 'string') detail = body.detail
    } catch {
      // cuerpo vacío o no-JSON
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  getLeads(
    empresaId: string,
    params: {
      temperatura?: string
      canal?: string
      ciudad?: string
      asesor_id?: string
      sin_contacto_24h?: boolean
      pagina?: number
      por_pagina?: number
    } = {},
  ): Promise<LeadListResponse> {
    return request<LeadListResponse>('/leads', { query: params }, empresaId)
  },

  getAsesores(empresaId: string): Promise<AsesoresResponse> {
    return request<AsesoresResponse>('/asesores', {}, empresaId)
  },

  getLeadsHoy(
    empresaId: string,
    asesorId: string,
    soloPendientes = false,
  ): Promise<MisLeadsHoyResponse> {
    return request<MisLeadsHoyResponse>(
      `/asesores/${asesorId}/leads-hoy`,
      { query: { solo_pendientes: soloPendientes } },
      empresaId,
    )
  },

  marcarAtendido(
    empresaId: string,
    asesorId: string,
    leadId: string,
  ): Promise<MensajeResponse> {
    return request<MensajeResponse>(
      `/asesores/${asesorId}/leads-hoy/${leadId}/atendido`,
      { method: 'PATCH' },
      empresaId,
    )
  },

  getPipelineStatus(): Promise<PipelineStatus> {
    return request<PipelineStatus>('/pipeline/status')
  },

  dispararPipeline(): Promise<MensajeResponse> {
    return request<MensajeResponse>('/pipeline/run', { method: 'POST' })
  },
}