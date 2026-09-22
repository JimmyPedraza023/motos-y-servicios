# Implementation Plan: Reemplazo de Streamlit por React

## Overview

Reemplazar el dashboard Streamlit (`dashboard/`) por un frontend React (Vite + TypeScript + Tailwind CSS) que consume la misma API FastAPI (`api/`). **El backend no cambia**: los contratos de `/leads`, `/asesores`, `/pipeline` y el header `X-Empresa-ID` se consumen tal cual. El código Streamlit se mantiene temporalmente (`dashboard/`) y se eliminará en una PR posterior.

## Architecture Decisions

- **Vite + React 18 + TypeScript** en una carpeta nueva `frontend/` (SPA). Build estático que se despliega como servicio independiente, igual que Streamlit Cloud hoy.
- **Tailwind CSS v4** para estilos (utilitarios, consistente con el dashboard actual sin librería de componentes).
- **API client con `fetch`** (sin axios) y tipado de las respuestas en `src/api/types.ts` derivado de `api/schemas.py` (Pydantic). El header `X-Empresa-ID` se envía en cada request, igual que `dashboard/api_client.py`.
- **Proxy de Vite** en dev: `/api` → `http://localhost:8000` para evitar CORS en local. La API ya expone CORS `allow_origins=["*"]` de todos modos.
- **Vistas replicadas 1:1** del Streamlit: (1) Leads priorizados con filtros, (2) Mis leads de hoy por asesor con marcar-atendido, (3) Estado del pipeline + disparo manual (botón deshabilitado en producción).
- **Sin tests del backend**: no se toca `python/`. La verificación es `npm run build` + `npm run lint` + revisión manual.
- **No se borra `dashboard/`** en esta rama (decisión del usuario). Solo se añade `frontend/` + configuración raíz mínima (`.gitignore`).

## Task List

### Phase 1: Base del frontend

- [ ] Task 1: Scaffold `frontend/` con Vite (react-ts) + Tailwind v4
- [ ] Task 2: Cliente API tipado (`src/api/`) con `X-Empresa-ID` y proxy dev

### Checkpoint: Foundation
- [ ] `npm run build` pasa limpio
- [ ] `/api/health` responde a través del proxy de Vite

### Phase 2: Vistas

- [ ] Task 3: Layout base (header + selector de empresa) y ruta "Leads priorizados" (tabla + métricas + filtros)
- [ ] Task 4: Vista "Mis leads de hoy" (selector de asesor, métricas, cards, marcar atendido)
- [ ] Task 5: Vista "Pipeline" (estado del último run, métricas, botón disparo deshabilitado)

### Checkpoint: Vistas
- [ ] Las 3 secciones del Streamlit quedan cubiertas en React con los mismos datos
- [ ] Flujo end-to-end: select empresa → filtros → tabla funciona contra la API local

### Phase 3: Pulido

- [ ] Task 6: README/doc de ejecución del frontend + línea en `.gitignore` para `node_modules/` y `dist/`

### Checkpoint: Complete
- [ ] `npm run build` limpio, `npm run lint` limpio
- [ ] Revisión humana del diff antes de push

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| CORS en producción (dominios distintos) | Med | La API ya tiene `allow_origins=["*"]`; en producción apuntar `VITE_API_BASE_URL` al dominio de Render |
| Respuestas `datetime` como strings ISO | Bajo | Tipar con `string` e introducir helper `formatear_fecha` (replicado de `dashboard/utils.py`) |
| Tailwind v4 con Vite carga CSS | Bajo | Usar el plugin oficial `@tailwindcss/vite`, no PostCSS legacy |
| Tabla de 1500 leads | Bajo | Paginación del backend (`por_pagina`), misma estrategia que el Streamlit actual |

## Open Questions

- URL de la API en producción (Render). Se resuelve con variable `VITE_API_BASE_URL` en `.env` del frontend.