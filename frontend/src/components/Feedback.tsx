export function Spinner({ text = 'Cargando...' }: { text?: string }) {
  return (
    <div className="flex items-center gap-3 py-6 text-gray-500 dark:text-gray-400">
      <div className="h-4 w-4 animate-spin rounded-full border-2 border-gray-300 border-t-indigo-600" />
      <span>{text}</span>
    </div>
  )
}

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-300 dark:border-red-800 bg-red-50 dark:bg-red-950 px-4 py-3 text-sm text-red-700 dark:text-red-300">
      {message}
    </div>
  )
}

export function EmptyState({ message }: { message: string }) {
  return <p className="py-4 text-sm text-gray-500 dark:text-gray-400">{message}</p>
}