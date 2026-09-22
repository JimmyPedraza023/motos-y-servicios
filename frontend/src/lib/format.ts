const TZ = 'America/Bogota'

export const TEMP_CONFIG: Record<string, { color: string; emoji: string; label: string }> = {
  Caliente: { color: '#ef4444', emoji: '🔴', label: 'Caliente' },
  Tibio: { color: '#f97316', emoji: '🟡', label: 'Tibio' },
  Frio: { color: '#3b82f6', emoji: '🔵', label: 'Frío' },
}

export const CANAL_EMOJI: Record<string, string> = {
  WhatsApp: '💬',
  'Meta Ads': '📱',
  'Formulario Web': '🌐',
}

export function fmtScore(score: number | null | undefined): string {
  if (score === null || score === undefined || Number.isNaN(score)) return '—'
  return score.toFixed(1)
}

export function fmtFecha(iso: string | null | undefined): string {
  if (!iso) return '—'
  const fecha = new Date(iso)
  if (Number.isNaN(fecha.getTime())) return '—'
  return new Intl.DateTimeFormat('es-CO', {
    timeZone: TZ,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(fecha)
}

export function fmtDuracion(iniciadoEn: string | null | undefined, finalizadoEn: string | null | undefined): string {
  if (!iniciadoEn || !finalizadoEn) return '—'
  const ini = new Date(iniciadoEn).getTime()
  const fin = new Date(finalizadoEn).getTime()
  if (Number.isNaN(ini) || Number.isNaN(fin)) return '—'
  return `${Math.round((fin - ini) / 1000)}s`
}

export function iconoTemperatura(temperatura: string | null | undefined): string {
  if (!temperatura) return '⚪'
  return TEMP_CONFIG[temperatura]?.emoji ?? '⚪'
}

export function labelTemperatura(temperatura: string | null | undefined): string {
  if (!temperatura) return 'Sin score'
  return TEMP_CONFIG[temperatura]?.label ?? temperatura
}

export function canalConEmoji(canal: string | null | undefined): string {
  if (!canal) return '—'
  return `${CANAL_EMOJI[canal] ?? '📋'} ${canal}`
}