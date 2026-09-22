import { useState } from 'react'
import { HoyView } from './views/HoyView'
import { LeadsView } from './views/LeadsView'
import { PipelineView } from './views/PipelineView'

const EMPRESAS = ['EMP-01', 'EMP-02', 'EMP-03']

type View = 'leads' | 'hoy' | 'pipeline'

const VISTAS: Record<View, { label: string }> = {
  leads: { label: '📋 Leads priorizados' },
  hoy: { label: '👤 Mis leads de hoy' },
  pipeline: { label: '⚙️ Pipeline' },
}

export default function App() {
  const [empresaId, setEmpresaId] = useState(EMPRESAS[0])
  const [vista, setVista] = useState<View>('leads')

  return (
    <div className="min-h-screen bg-gray-100 text-gray-900 dark:bg-gray-950 dark:text-gray-100">
      <header className="border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <h1 className="text-xl font-bold">🏍️ Motos &amp; Servicios</h1>
          <div className="flex items-center gap-2">
            <label htmlFor="select-empresa" className="text-sm text-gray-500 dark:text-gray-400">
              Empresa
            </label>
            <select
              id="select-empresa"
              value={empresaId}
              onChange={(e) => setEmpresaId(e.target.value)}
              className="rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-1.5 text-sm"
            >
              {EMPRESAS.map((e) => (
                <option key={e} value={e}>
                  {e}
                </option>
              ))}
            </select>
          </div>
        </div>
      </header>

      <nav className="border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
        <div className="mx-auto flex max-w-7xl gap-1 overflow-x-auto px-4">
          {(Object.keys(VISTAS) as View[]).map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => setVista(key)}
              className={`whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium ${
                vista === key
                  ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400'
                  : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
              }`}
            >
              {VISTAS[key].label}
            </button>
          ))}
        </div>
      </nav>

      <main className="mx-auto max-w-7xl px-4 py-6">
        {vista === 'leads' && <LeadsView empresaId={empresaId} />}
        {vista === 'hoy' && <HoyView key={empresaId} empresaId={empresaId} />}
        {vista === 'pipeline' && <PipelineView />}
      </main>
    </div>
  )
}