import os
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from api_client import (
    get_leads,
    get_asesores,
    get_leads_hoy,
    marcar_atendido,
    get_pipeline_status,
    disparar_pipeline,
)
from utils import badge_temperatura, badge_canal, fmt_score, color_temperatura

# ── Configuración ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Motos & Servicios — Leads",
    page_icon="🏍️",
    layout="wide",
)

# ── CSS mínimo ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Oculta la navbar superior de Streamlit */
    header[data-testid="stHeader"] { display: none !important; }
    /* Elimina el espacio que dejaba la navbar */
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# HEADER — empresa siempre visible
# ═══════════════════════════════════════════════════════════════════════════════
EMPRESAS = {
    "EMP-01": "EMP-01",
    "EMP-02": "EMP-02",
    "EMP-03": "EMP-03",
}

col_logo, col_spacer, col_empresa = st.columns([3, 4, 2])
with col_logo:
    st.markdown("## 🏍️ Motos & Servicios")
with col_empresa:
    # ← agregar este markdown antes del selectbox
    st.markdown("""
    <div style="margin-top: 14px;"></div>
    """, unsafe_allow_html=True)
    empresa_id = st.selectbox(
        "Empresa",
        options=list(EMPRESAS.keys()),
        format_func=lambda e: EMPRESAS[e],
        label_visibility="collapsed",
    )

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 1 — LEADS PRIORIZADOS
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("### 📋 Leads priorizados")
# ── Carga de leads ────────────────────────────────────────────────────────────
with st.spinner("Cargando leads..."):
    try:
        resp = get_leads(
            empresa_id=empresa_id,
            por_pagina=1500,
        )
        todos_los_leads = resp.get("data", [])
        total_empresa   = resp.get("total", 0)
    except Exception as e:
        st.error(f"Error al cargar leads: {e}")
        todos_los_leads, total_empresa = [], 0

# ── Filtros — construidos con datos reales ────────────────────────────────────
col_f1, col_f2, col_f3, col_f4 = st.columns([2, 2, 2, 2])

with col_f1:
    fil_temperatura = st.selectbox(
        "Temperatura",
        ["Todas", "Caliente", "Tibio", "Frio"],
        key="fil_temp",
    )
with col_f2:
    fil_canal = st.selectbox(
        "Canal",
        ["Todos", "WhatsApp", "Meta Ads", "Formulario Web"],
        key="fil_canal",
    )
with col_f3:
    ciudades_disponibles = sorted(set(
        l.get("ciudad", "") for l in todos_los_leads if l.get("ciudad")
    ))
    fil_ciudad = st.selectbox(
        "Ciudad",
        ["Todas"] + ciudades_disponibles,
        key="fil_ciudad",
    )
with col_f4:
    fil_asesor_leads = st.text_input(
        "Asesor ID", placeholder="AS-001...", key="fil_asesor"
    )

# ── Filtrado en cliente ───────────────────────────────────────────────────────
leads = todos_los_leads

if fil_temperatura != "Todas":
    leads = [
        l for l in leads
        if (l.get("score") or {}).get("temperatura") == fil_temperatura
    ]
if fil_canal != "Todos":
    leads = [l for l in leads if l.get("canal") == fil_canal]

if fil_ciudad != "Todas":
    leads = [l for l in leads if l.get("ciudad") == fil_ciudad]

if fil_asesor_leads:
    leads = [
        l for l in leads
        if (l.get("asignacion") or {}).get("asesor_id") == fil_asesor_leads
    ]
 

total = len(leads)

# ── Métricas ──────────────────────────────────────────────────────────────────
calientes = sum(1 for l in leads if (l.get("score") or {}).get("temperatura") == "Caliente")
tibios    = sum(1 for l in leads if (l.get("score") or {}).get("temperatura") == "Tibio")
frios     = sum(1 for l in leads if (l.get("score") or {}).get("temperatura") == "Frio")
alertas   = sum(1 for l in leads if not l.get("fecha_primer_contacto") and l.get("fecha_registro"))

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Total leads", total)
m2.metric("🔴 Calientes", calientes)
m3.metric("🟡 Tibios", tibios)
m4.metric("🔵 Fríos", frios)
m5.metric("⚠️ Sin contacto", alertas)

# ── Tabla ─────────────────────────────────────────────────────────────────────
if not leads:
    st.info("No hay leads con los filtros aplicados.")
else:
    filas = []
    for i, l in enumerate(leads, 1):
        score = l.get("score") or {}
        asig  = l.get("asignacion") or {}
        filas.append({
            "#":       i,
            "Lead ID": l["lead_id"],
            "Cliente": l.get("nombre_cliente", "—"),
            "Modelo":  l.get("modelo_interes_texto", "—"),
            "Temp.":   badge_temperatura(score.get("temperatura")),
            "Score":   fmt_score(score.get("score_total")),
            "Canal":   badge_canal(l.get("canal", "")),
            "Ciudad":  l.get("ciudad", "—"),
            "Estado":  l.get("estado_gestion", "—"),
            "Asesor":  asig.get("asesor_id", "—"),
        })

    df = pd.DataFrame(filas)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=350,
        column_config={
            "#":       st.column_config.NumberColumn(width="small"),
            "Score":   st.column_config.TextColumn(width="small"),
            "Temp.":   st.column_config.TextColumn(width="small"),
            "Lead ID": st.column_config.TextColumn(width="medium"),
        },
    )

# ═══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 2 — MIS LEADS DE HOY
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("### 👤 Mis leads de hoy")

# ── Selector de asesor ────────────────────────────────────────────────────────
try:
    asesores_resp = get_asesores(empresa_id)
    asesores = asesores_resp.get("data", [])
except Exception as e:
    st.error(f"Error al cargar asesores: {e}")
    asesores = []

col_as1, col_as2 = st.columns([3, 1])
with col_as1:
    if asesores:
        asesor_opciones = {
            f"{a['nombre']} ({a['asesor_id']})": a["asesor_id"]
            for a in asesores
        }
        asesor_label  = st.selectbox("Asesor", list(asesor_opciones.keys()), key="sel_asesor")
        asesor_id_hoy = asesor_opciones[asesor_label]
    else:
        st.warning("No hay asesores activos para esta empresa.")
        asesor_id_hoy = None

    solo_pendientes = False  # siempre muestra todos los leads

if asesor_id_hoy:
    try:
        resp_hoy = get_leads_hoy(empresa_id, asesor_id_hoy, solo_pendientes)
        leads_hoy    = resp_hoy.get("leads", [])
        total_asig   = resp_hoy.get("total_asignados", 0)
        total_aten   = resp_hoy.get("total_atendidos", 0)
        fecha_gestion = resp_hoy.get("fecha", "—")
        run_id        = resp_hoy.get("pipeline_run_id", "—")
    except Exception as e:
        st.error(f"Error al cargar leads del asesor: {e}")
        leads_hoy, total_asig, total_aten = [], 0, 0
        fecha_gestion, run_id = "—", "—"

    # ── Métricas del asesor ───────────────────────────────────────────────────
    h1, h2, h3, h4 = st.columns(4)
    h1.metric("📅 Fecha gestión", fecha_gestion)
    h2.metric("📋 Asignados",     total_asig)
    h3.metric("✅ Atendidos",     total_aten)
    h4.metric("⏳ Pendientes",    total_asig - total_aten)

    if total_asig > 0:
        st.progress(
            total_aten / total_asig,
            text=f"Progreso: {total_aten}/{total_asig}",
        )
    st.caption(f"Run ID: `{run_id}`")

    # ── Lista de leads del asesor ─────────────────────────────────────────────
    if not leads_hoy:
        st.success("Sin leads pendientes para este asesor hoy." if solo_pendientes
                   else "Este asesor no tiene leads asignados hoy.")
    else:
        for idx, lead in enumerate(leads_hoy):
            temp     = lead.get("temperatura")
            atendido = lead.get("atendido", False)
            alerta   = lead.get("alerta_sin_contacto", False)
            lead_id  = lead["lead_id"]

            icono = {"Caliente": "🔴", "Tibio": "🟡", "Frio": "🔵"}.get(temp, "⚪")

            with st.container(border=True):
                col_i, col_a = st.columns([5, 1])
                with col_i:
                    partes = [
                        f"**#{lead.get('orden_prioridad', '—')}**",
                        icono,
                        f"**{lead.get('nombre_cliente', 'Sin nombre')}**",
                        f"· Score: `{fmt_score(lead.get('score_total'))}`",
                        f"· {badge_canal(lead.get('canal', ''))}",
                    ]
                    if alerta:
                        partes.append("⚠️ **+24h sin contacto**")
                    if atendido:
                        partes.append("✅ *Atendido*")
                    st.markdown(" ".join(partes))

                    d1, d2, d3 = st.columns(3)
                    d1.markdown(f"📞 `{lead.get('telefono', '—')}`")
                    d2.markdown(f"📍 {lead.get('ciudad', '—')}")
                    d3.markdown(f"🏍️ {lead.get('modelo_interes_texto', '—')}")

                    if lead.get("explicacion"):
                        st.caption(lead["explicacion"])

                with col_a:
                    if not atendido:
                        if st.button("✅ Atendido", key=f"hoy_btn_{idx}_{lead_id}"):
                            try:
                                marcar_atendido(empresa_id, asesor_id_hoy, lead_id)
                                st.success("Marcado")
                                st.rerun()
                            except Exception as e:
                                st.error(str(e))
                    else:
                        st.markdown("✅")

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 3 — PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("### ⚙️ Pipeline")

try:
    status = get_pipeline_status()
except Exception as e:
    st.error(f"No se pudo obtener el estado del pipeline: {e}")
    status = {}

if status:
    estado = status.get("estado", "—")
    icono_estado = {"exitoso": "✅", "en_proceso": "🔄", "fallido": "❌"}.get(estado, "⚪")

    p1, p2, p3, p4, p5 = st.columns(5)
    p1.metric("Estado", f"{icono_estado} {estado.capitalize()}")
    p2.metric("Trigger", status.get("trigger_tipo", "—").capitalize())
    p3.metric("Leads procesados", status.get("leads_procesados", "—"))
    p4.metric("Leads asignados",  status.get("leads_asignados", "—"))

    # Duración
    with p5:
        ini = status.get("iniciado_en", "")
        fin = status.get("finalizado_en", "")
        if ini and fin:
            try:
                t_ini = datetime.fromisoformat(ini.replace("Z", "+00:00"))
                t_fin = datetime.fromisoformat(fin.replace("Z", "+00:00"))
                dur   = (t_fin - t_ini).total_seconds()
                st.metric("Duración", f"{dur:.0f}s")
            except Exception:
                st.metric("Duración", "—")

    # Timestamp y run_id
    st.caption(
        f"Última ejecución: `{status.get('iniciado_en', '—')}` · "
        f"Run ID: `{status.get('run_id', '—')}`"
    )

    if status.get("error_mensaje"):
        st.error(f"Error: {status['error_mensaje']}")

    # Auto-refresh si está en proceso
    if estado == "en_proceso":
        st.warning("Pipeline en ejecución — actualizando en 10 segundos...")
        st.markdown(
            '<meta http-equiv="refresh" content="10">',
            unsafe_allow_html=True,
        )