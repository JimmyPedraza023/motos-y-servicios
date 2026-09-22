import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { LeadResponse } from '../api/types'
import { TemperaturaBadge, CanalBadge } from '../components/Badges'
import { EmptyState, ErrorBanner, Spinner } from '../components/Feedback'
import { Metric } from '../components/Metric'
import { fmtScore } from '../lib/format'

const TEMPERATURAS = ['Todas', 'Caliente', 'Tibio', 'Frio']
const CANALES = ['Todos', 'WhatsApp', 'Meta Ads', 'Formulario Web']
const POR_PAGINA = 1500

interface Props {
  empresaId: string
}

export function LeadsView({ empresaId }: Props) {
  const [leads, setLeads] = useState<LeadResponse[]>([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [temperatura, setTemperatura] = useState('Todas')
  const [canal, setCanal] = useState('Todos')
  const [ciudad, setCiudad] = useState('Todas')
  const [asesorId, setAsesorId] = useState('')

  const cargar = useCallback(async () => {
    try {
      const resp = await api.getLeads(empresaId, { por_pagina: POR_PAGINA })
      setLeads(resp.data)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error al cargar leads')
    } finally {
      setCargando(false)
    }
  }, [empresaId])

  useEffect(() => {
    void cargar()
  }, [cargar])

  const ciudades = useMemo(
    () => Array.from(new Set(leads.map((l) => l.ciudad).filter((c): c is string => Boolean(c)))).sort(),
    [leads],
  )

  const filtrados = useMemo(() => {
    const asesor = asesorId.trim()
    return leads.filter((l) => {
      if (temperatura !== 'Todas' && l.score?.temperatura !== temperatura) return false
      if (canal !== 'Todos' && l.canal !== canal) return false
      if (ciudad !== 'Todas' && l.ciudad !== ciudad) return false
      if (asesor && l.asignacion?.asesor_id !== asesor) return false
      return true
    })
  }, [leads, temperatura, canal, ciudad, asesorId])

  const metricas = useMemo(() => {
    const calientes = filtrados.filter((l) => l.score?.temperatura === 'Caliente').length
    const tibios = filtrados.filter((l) => l.score?.temperatura === 'Tibio').length
    const frios = filtrados.filter((l) => l.score?.temperatura === 'Frio').length
    const sinContacto = filtrados.filter((l) => !l.fecha_primer_contacto && l.fecha_registro).length
    return { total: filtrados.length, calientes, tibios, frios, sinContacto }
  }, [filtrados])

  return (
    <section>
      <h2 className="mb-4 text-lg font-semibold">📋 Leads priorizados</h2>

      {cargando && <Spinner text="Cargando leads..." />}
      {!cargando && error && <ErrorBanner message={error} />}

      {!cargando && !error && (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
            <select
              aria-label="Temperatura"
              value={temperatura}
              onChange={(e) => setTemperatura(e.target.value)}
              className="rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm"
            >
              {TEMPERATURAS.map((t) => (
                <option key={t} value={t}>
                  {t === 'Todas' ? '🌡️ Temperatura' : t}
                </option>
              ))}
            </select>
            <select
              aria-label="Canal"
              value={canal}
              onChange={(e) => setCanal(e.target.value)}
              className="rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm"
            >
              {CANALES.map((c) => (
                <option key={c} value={c}>
                  {c === 'Todos' ? '📢 Canal' : c}
                </option>
              ))}
            </select>
            <select
              aria-label="Ciudad"
              value={ciudad}
              onChange={(e) => setCiudad(e.target.value)}
              className="rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm"
            >
              <option value="Todas">📍 Ciudad</option>
              {ciudades.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <input
              type="text"
              aria-label="Asesor ID"
              placeholder="Asesor ID (AS-001...)"
              value={asesorId}
              onChange={(e) => setAsesorId(e.target.value)}
              className="rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm"
            />
          </div>

          <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-5">
            <Metric label="Total leads" value={metricas.total} />
            <Metric label="🔴 Calientes" value={metricas.calientes} accent />
            <Metric label="🟡 Tibios" value={metricas.tibios} />
            <Metric label="🔵 Fríos" value={metricas.frios} />
            <Metric label="⚠️ Sin contacto" value={metricas.sinContacto} />
          </div>

          {filtrados.length === 0 ? (
            <EmptyState message="No hay leads con los filtros aplicados." />
          ) : (
            <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
              <table className="w-full min-w-[900px] text-left text-sm">
                <thead className="bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-300">
                  <tr>
                    <th className="px-3 py-2 font-medium">#</th>
                    <th className="px-3 py-2 font-medium">Lead ID</th>
                    <th className="px-3 py-2 font-medium">Cliente</th>
                    <th className="px-3 py-2 font-medium">Modelo</th>
                    <th className="px-3 py-2 font-medium">Temp.</th>
                    <th className="px-3 py-2 font-medium">Score</th>
                    <th className="px-3 py-2 font-medium">Canal</th>
                    <th className="px-3 py-2 font-medium">Ciudad</th>
                    <th className="px-3 py-2 font-medium">Estado</th>
                    <th className="px-3 py-2 font-medium">Asesor</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                  {filtrados.map((l, i) => (
                    <tr key={l.lead_id} className="odd:bg-white even:bg-gray-50 dark:odd:bg-gray-900 dark:even:bg-gray-800">
                      <td className="px-3 py-2 text-gray-500 dark:text-gray-400">{i + 1}</td>
                      <td className="px-3 py-2 font-mono text-xs">{l.lead_id}</td>
                      <td className="px-3 py-2">{l.nombre_cliente ?? '—'}</td>
                      <td className="px-3 py-2">{l.modelo_interes_texto ?? '—'}</td>
                      <td className="px-3 py-2">
                        <TemperaturaBadge temperatura={l.score?.temperatura} />
                      </td>
                      <td className="px-3 py-2 font-mono">{fmtScore(l.score?.score_total)}</td>
                      <td className="px-3 py-2">
                        <CanalBadge canal={l.canal} />
                      </td>
                      <td className="px-3 py-2">{l.ciudad ?? '—'}</td>
                      <td className="px-3 py-2">{l.estado_gestion ?? '—'}</td>
                      <td className="px-3 py-2 font-mono text-xs">{l.asignacion?.asesor_id ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  )
}