import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { AsesorResponse, MisLeadsHoyResponse } from '../api/types'
import { TemperaturaBadge, CanalBadge } from '../components/Badges'
import { EmptyState, ErrorBanner, Spinner } from '../components/Feedback'
import { Metric } from '../components/Metric'
import { fmtFecha, fmtScore } from '../lib/format'

interface Props {
  empresaId: string
}

export function HoyView({ empresaId }: Props) {
  const [asesores, setAsesores] = useState<AsesorResponse[]>([])
  const [asesorSeleccionado, setAsesorSeleccionado] = useState<string>('')
  const [datos, setDatos] = useState<MisLeadsHoyResponse | null>(null)
  const [cargandoAsesores, setCargandoAsesores] = useState(true)
  const [cargandoLeads, setCargandoLeads] = useState(false)
  const [errorAsesores, setErrorAsesores] = useState<string | null>(null)
  const [errorLeads, setErrorLeads] = useState<string | null>(null)
  const [marcandoId, setMarcandoId] = useState<string | null>(null)

  useEffect(() => {
    let activo = true
    api
      .getAsesores(empresaId)
      .then((resp) => {
        if (!activo) return
        setAsesores(resp.data)
        if (resp.data.length > 0) setAsesorSeleccionado(resp.data[0].asesor_id)
      })
      .catch((e) => {
        if (!activo) return
        setErrorAsesores(e instanceof Error ? e.message : 'Error al cargar asesores')
      })
      .finally(() => {
        if (activo) setCargandoAsesores(false)
      })
    return () => {
      activo = false
    }
  }, [empresaId])

  const cargarLeads = useCallback(async () => {
    if (!asesorSeleccionado) return
    setCargandoLeads(true)
    setErrorLeads(null)
    try {
      const resp = await api.getLeadsHoy(empresaId, asesorSeleccionado, false)
      setDatos(resp)
    } catch (e) {
      setErrorLeads(e instanceof Error ? e.message : 'Error al cargar leads del asesor')
      setDatos(null)
    } finally {
      setCargandoLeads(false)
    }
  }, [empresaId, asesorSeleccionado])

  useEffect(() => {
    void cargarLeads()
  }, [cargarLeads])

  const opciones = useMemo(
    () =>
      asesores.map((a) => ({
        value: a.asesor_id,
        label: `${a.nombre} (${a.asesor_id})`,
      })),
    [asesores],
  )

  const asesorNombre = useMemo(
    () => asesores.find((a) => a.asesor_id === asesorSeleccionado)?.nombre ?? asesorSeleccionado,
    [asesores, asesorSeleccionado],
  )

  const marcarAtendido = async (leadId: string) => {
    setMarcandoId(leadId)
    try {
      await api.marcarAtendido(empresaId, asesorSeleccionado, leadId)
      await cargarLeads()
    } catch (e) {
      setErrorLeads(e instanceof Error ? e.message : 'No se pudo marcar como atendido')
    } finally {
      setMarcandoId(null)
    }
  }

  return (
    <section>
      <h2 className="mb-4 text-lg font-semibold">👤 Mis leads de hoy</h2>

      {cargandoAsesores && <Spinner text="Cargando asesores..." />}
      {!cargandoAsesores && errorAsesores && <ErrorBanner message={errorAsesores} />}

      {!cargandoAsesores && !errorAsesores && asesores.length === 0 && (
        <EmptyState message="No hay asesores activos para esta empresa." />
      )}

      {!cargandoAsesores && !errorAsesores && asesores.length > 0 && (
        <>
          <div className="mb-4 w-full max-w-md">
            <label htmlFor="select-asesor" className="mb-1 block text-sm text-gray-500 dark:text-gray-400">
              Asesor
            </label>
            <select
              id="select-asesor"
              value={asesorSeleccionado}
              onChange={(e) => setAsesorSeleccionado(e.target.value)}
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm"
            >
              {opciones.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>

          {cargandoLeads && <Spinner text="Cargando leads del asesor..." />}
          {!cargandoLeads && errorLeads && <ErrorBanner message={errorLeads} />}

          {!cargandoLeads && !errorLeads && datos && (
            <>
              <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
                <Metric label="📅 Fecha gestión" value={datos.fecha} />
                <Metric label="📋 Asignados" value={datos.total_asignados} />
                <Metric label="✅ Atendidos" value={datos.total_atendidos} />
                <Metric label="⏳ Pendientes" value={datos.total_asignados - datos.total_atendidos} />
              </div>

              {datos.total_asignados > 0 && (
                <div className="mb-2">
                  <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
                    <div
                      className="h-full bg-indigo-600"
                      style={{
                        width: `${(datos.total_atendidos / datos.total_asignados) * 100}%`,
                      }}
                    />
                  </div>
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    Progreso: {datos.total_atendidos}/{datos.total_asignados} · Run ID:{' '}
                    <code className="rounded bg-gray-100 dark:bg-gray-700 px-1">{datos.pipeline_run_id ?? '—'}</code>
                  </p>
                </div>
              )}

              {datos.leads.length === 0 ? (
                <EmptyState message="Este asesor no tiene leads asignados hoy." />
              ) : (
                <ul className="space-y-3">
                  {datos.leads.map((lead) => {
                    const atendido = lead.atendido
                    return (
                      <li
                        key={lead.lead_id}
                        className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4"
                      >
                        {atendido && (
                          <div className="mb-3 flex items-center gap-2 rounded-md bg-green-50 dark:bg-green-950 px-3 py-1.5 text-sm font-medium text-green-700 dark:text-green-300">
                            ✅ Atendido
                          </div>
                        )}

                        <div className="flex items-start justify-between gap-4">
                          <div className="min-w-0 flex-1 space-y-2">
                            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                              <span className="text-sm font-medium text-gray-500 dark:text-gray-400">
                                #{lead.orden_prioridad ?? '—'}
                              </span>
                              <span className="font-semibold">{lead.nombre_cliente ?? 'Sin nombre'}</span>
                              <TemperaturaBadge temperatura={lead.temperatura} />
                              <span className="font-mono text-sm text-gray-600 dark:text-gray-300">
                                Score: {fmtScore(lead.score_total)}
                              </span>
                              <CanalBadge canal={lead.canal} />
                              {lead.alerta_sin_contacto && (
                                <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 dark:bg-amber-900 px-2 py-0.5 text-xs font-semibold text-amber-800 dark:text-amber-200">
                                  ⚠️ +24h sin contacto
                                </span>
                              )}
                            </div>

                            <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-gray-600 dark:text-gray-300">
                              <span>📞 {lead.telefono ?? '—'}</span>
                              <span>📍 {lead.ciudad ?? '—'}</span>
                              <span>🏍️ {lead.modelo_interes_texto ?? '—'}</span>
                            </div>

                            {lead.temperatura && (
                              <p className="text-xs text-gray-500 dark:text-gray-400">
                                Registro: {fmtFecha(lead.fecha_registro)}
                              </p>
                            )}

                            {lead.explicacion && (
                              <p className="text-xs text-gray-500 dark:text-gray-400">{lead.explicacion}</p>
                            )}
                          </div>

                          <div className="shrink-0">
                            {atendido ? (
                              <span className="text-xl" aria-hidden="true">
                                ✅
                              </span>
                            ) : (
                              <button
                                type="button"
                                disabled={marcandoId === lead.lead_id}
                                onClick={() => void marcarAtendido(lead.lead_id)}
                                className="rounded-md bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
                              >
                                {marcandoId === lead.lead_id ? 'Marcando...' : '✅ Atendido'}
                              </button>
                            )}
                          </div>
                        </div>
                      </li>
                    )
                  })}
                </ul>
              )}
              <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">
                Asesor: {asesorNombre} · Fecha: {datos.fecha}
              </p>
            </>
          )}
        </>
      )}
    </section>
  )
}