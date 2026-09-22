import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import type { PipelineStatus } from '../api/types'
import { EmptyState, ErrorBanner, Spinner } from '../components/Feedback'
import { Metric } from '../components/Metric'
import { fmtDuracion, fmtFecha } from '../lib/format'

const ICONOS_ESTADO: Record<string, string> = {
  exitoso: '✅',
  en_proceso: '🔄',
  fallido: '❌',
}

const REFRESH_MS = 10000

export function PipelineView() {
  const [status, setStatus] = useState<PipelineStatus | null>(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    try {
      const resp = await api.getPipelineStatus()
      setStatus(resp)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo obtener el estado del pipeline')
    } finally {
      setCargando(false)
    }
  }, [])

  useEffect(() => {
    void cargar()
  }, [cargar])

  const enProceso = status?.estado === 'en_proceso'

  useEffect(() => {
    if (!enProceso) return
    const timer = window.setInterval(() => void cargar(), REFRESH_MS)
    return () => window.clearInterval(timer)
  }, [enProceso, cargar])

  const estado = status?.estado ?? '—'
  const iconoEstado = ICONOS_ESTADO[estado] ?? '⚪'

  return (
    <section>
      <h2 className="mb-4 text-lg font-semibold">⚙️ Pipeline</h2>

      {cargando && <Spinner text="Consultando estado del pipeline..." />}
      {!cargando && error && <ErrorBanner message={error} />}

      {!cargando && !error && !status && <EmptyState message="No hay runs registrados aún." />}

      {!cargando && !error && status && (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
            <Metric label="Estado" value={`${iconoEstado} ${estado.charAt(0).toUpperCase() + estado.slice(1)}`} accent />
            <Metric label="Trigger" value={(status.trigger_tipo ?? '—').charAt(0).toUpperCase() + (status.trigger_tipo ?? '—').slice(1)} />
            <Metric label="Leads procesados" value={status.leads_procesados ?? '—'} />
            <Metric label="Leads asignados" value={status.leads_asignados ?? '—'} />
          </div>

          <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-3">
            <Metric label="Duración" value={fmtDuracion(status.iniciado_en, status.finalizado_en)} />
            <Metric label="Última ejecución" value={fmtFecha(status.iniciado_en)} />
            <Metric label="Run ID" value={status.run_id ?? '—'} />
          </div>

          {enProceso && (
            <div className="mb-4 rounded-lg border border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-950 px-4 py-3 text-sm text-amber-800 dark:text-amber-200">
              🔄 Pipeline en ejecución — actualizando cada 10 segundos...
            </div>
          )}

          {status.error_mensaje && <ErrorBanner message={`Error: ${status.error_mensaje}`} />}

          <hr className="my-4 border-gray-200 dark:border-gray-700" />

          <button
            type="button"
            disabled
            title="Disparo manual disponible vía POST /pipeline/run en la API. En producción se ejecuta automáticamente cada noche a las 02:00 COT."
            className="cursor-not-allowed rounded-md bg-gray-300 dark:bg-gray-700 px-4 py-2 text-sm font-medium text-gray-600 dark:text-gray-300"
          >
            ⚡ Ejecutar pipeline ahora
          </button>
          <p className="mt-2 max-w-xl text-xs text-gray-500 dark:text-gray-400">
            Disparo manual disponible vía POST /pipeline/run en la API. En producción se ejecuta automáticamente cada
            noche a las 02:00 COT.
          </p>
        </>
      )}
    </section>
  )
}