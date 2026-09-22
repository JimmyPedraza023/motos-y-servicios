interface MetricProps {
  label: string
  value: string | number
  accent?: boolean
}

export function Metric({ label, value, accent = false }: MetricProps) {
  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-4 py-3">
      <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
      <p
        className={`mt-1 text-2xl font-semibold ${
          accent ? 'text-indigo-600 dark:text-indigo-400' : ''
        }`}
      >
        {value}
      </p>
    </div>
  )
}