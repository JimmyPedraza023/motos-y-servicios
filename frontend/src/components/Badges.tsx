import { canalConEmoji, labelTemperatura, TEMP_CONFIG } from '../lib/format'

export function TemperaturaBadge({ temperatura }: { temperatura: string | null | undefined }) {
  const config = temperatura ? TEMP_CONFIG[temperatura] : undefined
  if (!config) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-gray-200 dark:bg-gray-700 px-2 py-0.5 text-xs font-medium text-gray-700 dark:text-gray-200">
        ⚪ Sin score
      </span>
    )
  }
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold text-white"
      style={{ backgroundColor: config.color }}
    >
      {config.emoji} {labelTemperatura(temperatura)}
    </span>
  )
}

export function CanalBadge({ canal }: { canal: string | null | undefined }) {
  return <span className="text-sm whitespace-nowrap">{canalConEmoji(canal)}</span>
}