# Tasks — Reemplazo de Streamlit por React

## Task 1: Scaffold `frontend/` con Vite + Tailwind

**Description:** Crear el proyecto React-Vite-TypeScript en `frontend/` con Tailwind CSS v4 y limpiar el boilerplate de Vite.

**Acceptance criteria:**
- [ ] `npm create vite@latest frontend -- --template react-ts` ejecutado (o scaffold manual equivalente)
- [ ] Tailwind v4 instalado y conectado al build (plugin `@tailwindcss/vite`)
- [ ] `npm run dev` arranca y muestra una página base
- [ ] Boilerplate de Vite reemplazado por una estructura de app propia

**Verification:**
- [ ] Tests pass: n/a (frontend sin tests aún)
- [ ] Build succeeds: `npm run build` en `frontend/`
- [ ] Manual check: `npm run dev` abre `http://localhost:5173`

**Dependencies:** None

**Files likely touched:**
- `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig*.json`, `frontend/src/index.css`, `frontend/index.html`

**Estimated scope:** Small

## Task 2: Cliente API tipado + proxy dev

**Description:** Crear `frontend/src/api/` con fetch wrapper, tipos (derivados de `api/schemas.py`) y endpoints (leads, asesores, leads-hoy, marcar atendido, pipeline status/run). Configurar proxy `/api` en Vite hacia `http://localhost:8000`.

**Acceptance criteria:**
- [ ] Tipos: `LeadResponse`, `LeadListResponse`, `AsesorResponse`, `LeadDeHoyResponse`, `MisLeadsHoyResponse`, `PipelineStatus`
- [ ] Cliente envía header `X-Empresa-ID` en cada llamada
- [ ] Proxy de Vite: `/api` → `http://localhost:8000`
- [ ] Soporte `VITE_API_BASE_URL` para producción

**Verification:**
- [ ] Build succeeds: `npm run build`
- [ ] Manual check: `GET /api/health` responde vía el dev server

**Dependencies:** Task 1

**Files likely touched:**
- `frontend/src/api/client.ts`, `frontend/src/api/types.ts`
- `frontend/vite.config.ts`

**Estimated scope:** Small

## Checkpoint: Foundation (Tasks 1-2)
- [ ] `npm run build` pasa limpio
- [ ] `/api/health` responde a través del proxy

## Task 3: Layout + vista "Leads priorizados"

**Description:** Layout base (header con selector de empresa `EMP-01/02/03`, footer) y la tabla de leads priorizados replicando `dashboard/app.py`: métricas (total, calientes, tibios, fríos, sin contacto), filtros (temperatura, canal, ciudad, asesor), tabla ordenada por score.

**Acceptance criteria:**
- [ ] Selector de empresa cambia el header `X-Empresa-ID` y recarga datos
- [ ] Métricas y tabla reflejan la respuesta de `GET /leads`
- [ ] Filtros de temperatura/canal/ciudad/asesor aplican (backend + cliente, mismo comportamiento que Streamlit: carga `por_pagina=1500` y filtra en cliente)
- [ ] Badges de temperatura/canal y formato de score replicados (`dashboard/utils.py`)
- [ ] Fecha en zona Colombia (helper `formatear_fecha`)

**Verification:**
- [ ] Build succeeds: `npm run build`
- [ ] Manual check: contra API local, tabla muestra datos reales y filtros funcionan

**Dependencies:** Task 2

**Files likely touched:**
- `frontend/src/components/`, `frontend/src/views/LeadsView.tsx`, `frontend/src/lib/format.ts`

**Estimated scope:** Large (pero limitado a ~5 archivos; se puede dividir si crece)

## Task 4: Vista "Mis leads de hoy"

**Description:** Vista de asesor: selector de asesores (`GET /asesores`), métricas (fecha, asignados, atendidos, pendientes), barra de progreso, lista de cards de leads con score/temperatura/alertas y botón "Atendido" (`PATCH .../atendido`) que recarga la lista.

**Acceptance criteria:**
- [ ] Selector de asesor carga `GET /asesores/{id}/leads-hoy`
- [ ] Cards muestran nombre, teléfono, ciudad, modelo, score, badge temperatura, alerta +24h
- [ ] Botón "Atendido" llama al PATCH y refresca la lista
- [ ] Mensajes de estado vacío/sin asesores replicados

**Verification:**
- [ ] Build succeeds: `npm run build`
- [ ] Manual check: marcado de atendido persiste y la métrica cambia

**Dependencies:** Task 2

**Files likely touched:**
- `frontend/src/views/HoyView.tsx`, `frontend/src/components/LeadCard.tsx`

**Estimated scope:** Medium

## Task 5: Vista "Pipeline"

**Description:** Vista de estado del pipeline: métricas (estado, trigger, leads procesados, leads asignados, duración), run id/fecha, mensaje de error, auto-refresh cuando `en_proceso`, y botón de disparo manual deshabilitado (mismo comportamiento que Streamlit: disponible vía POST /pipeline/run).

**Acceptance criteria:**
- [ ] `GET /pipeline/status` renderiza métricas y timestamp en zona Colombia
- [ ] Si `en_proceso`, muestra aviso y refresca (poll cada ~10s)
- [ ] Botón disparo manual deshabilitado con tooltip explicativo

**Verification:**
- [ ] Build succeeds: `npm run build`
- [ ] Manual check: estado del último run renderiza datos reales

**Dependencies:** Task 2

**Files likely touched:**
- `frontend/src/views/PipelineView.tsx`

**Estimated scope:** Medium

## Checkpoint: Vistas (Tasks 3-5)
- [ ] Las 3 secciones del Streamlit quedan cubiertas en React con los mismos datos
- [ ] Flujo end-to-end funciona contra la API local

## Task 6: Docs + gitignore

**Description:** Actualizar `.gitignore` (raíz) para `node_modules/`, `dist/`, `*.local` del frontend. Añadir instrucciones de ejecución del frontend al `README.md` (fila en la tabla de comandos + nota de despliegue). No tocar nada de backend.

**Acceptance criteria:**
- [ ] `.gitignore` cubre `frontend/node_modules/` y `frontend/dist/`
- [ ] README documenta: `npm install`, `npm run dev`, `npm run build`, variable `VITE_API_BASE_URL`

**Verification:**
- [ ] `git status` no muestra `node_modules/` ni `dist/`

**Dependencies:** Tasks 3-5 (puede correrse en paralelo)

**Files likely touched:**
- `.gitignore`, `README.md`

**Estimated scope:** XS

## Checkpoint: Complete (Tasks 1-6)
- [ ] `npm run build` limpio
- [ ] `npm run lint` limpio
- [ ] Revisión humana del diff antes de push