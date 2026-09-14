"""
Exploración inicial de los archivos fuente.
Ejecutar: python pipeline/explore.py
No forma parte del pipeline productivo — es análisis previo.
"""

import json
import pandas as pd

RAW = "data/raw"

# ── Helpers ──────────────────────────────────────────────────────────────────

def separador(titulo: str):
    print(f"\n{'='*60}")
    print(f"  {titulo}")
    print('='*60)

def resumen_df(df: pd.DataFrame, nombre: str):
    separador(nombre)
    print(f"Filas: {len(df):,}  |  Columnas: {len(df.columns)}")
    print(f"\nColumnas: {list(df.columns)}")
    print(f"\nTipos:\n{df.dtypes}")
    print(f"\nNulos por columna:\n{df.isnull().sum()}")
    print(f"\nMuestra (3 filas):\n{df.head(3).to_string()}")

# ── 1. leads.csv ─────────────────────────────────────────────────────────────

leads = pd.read_csv(f"{RAW}/leads.csv")
resumen_df(leads, "leads.csv")

print("\n--- Valores únicos por columna categórica ---")
for col in ["canal", "empresa_id", "punto_venta_id", "estado_gestion", "ciudad"]:
    if col in leads.columns:
        print(f"\n{col}:\n{leads[col].value_counts(dropna=False).head(15)}")

print("\n--- Análisis de teléfonos ---")
print(f"Teléfonos nulos: {leads['telefono'].isnull().sum()}")
print(f"Teléfonos únicos: {leads['telefono'].nunique()}")
print(f"Muestra de formatos:\n{leads['telefono'].dropna().head(10).tolist()}")

print("\n--- Análisis de fechas ---")
print(f"Muestra fecha_registro:\n{leads['fecha_registro'].dropna().head(10).tolist()}")

print("\n--- Modelo de interés (texto libre) ---")
print(leads["modelo_interes_texto"].value_counts(dropna=False).head(20))

print("\n--- Posibles duplicados por teléfono ---")
tel_dup = leads[leads.duplicated(subset=["telefono"], keep=False) & leads["telefono"].notna()]
print(f"Leads con teléfono repetido: {len(tel_dup)}")
print(tel_dup[["lead_id", "telefono", "nombre_cliente", "canal", "empresa_id"]].head(10).to_string())

# ── 2. conversaciones.json ────────────────────────────────────────────────────

separador("conversaciones.json")
with open(f"{RAW}/conversaciones.json", "r", encoding="utf-8") as f:
    convs = json.load(f)

print(f"Total conversaciones: {len(convs)}")
print(f"\nEstructura de la primera conversación:")
primera = convs[0]
print(f"  Claves: {list(primera.keys())}")
print(f"  lead_id: {primera.get('lead_id')}")
print(f"  canal: {primera.get('canal')}")
print(f"  fecha_inicio: {primera.get('fecha_inicio')}")
print(f"  Total mensajes: {len(primera.get('mensajes', []))}")

print(f"\nPrimeros 3 mensajes:")
for msg in primera.get("mensajes", [])[:3]:
    print(f"  [{msg.get('emisor')}] {msg.get('hora')} — {msg.get('texto')[:80]}")

# Estadísticas de mensajes
longitudes = [len(c.get("mensajes", [])) for c in convs]
print(f"\nMensajes por conversación — min: {min(longitudes)}, max: {max(longitudes)}, promedio: {sum(longitudes)/len(longitudes):.1f}")

# ¿Cuántos lead_id de conversaciones existen en leads.csv?
leads_ids = set(leads["lead_id"].astype(str))
conv_lead_ids = {str(c.get("lead_id")) for c in convs}
print(f"\nlead_ids en conversaciones que existen en leads.csv: {len(conv_lead_ids & leads_ids)}")
print(f"lead_ids en conversaciones que NO existen en leads.csv: {len(conv_lead_ids - leads_ids)}")

# ── 3. catalogo_motos.csv ─────────────────────────────────────────────────────

catalogo = pd.read_csv(f"{RAW}/catalogo_motos.csv")
resumen_df(catalogo, "catalogo_motos.csv")
print("\n--- Marcas y segmentos ---")
print(catalogo[["marca", "segmento", "precio_lista"]].to_string())

# ── 4. asesores.csv ───────────────────────────────────────────────────────────

asesores = pd.read_csv(f"{RAW}/asesores.csv")
resumen_df(asesores, "asesores.csv")
print("\n--- Capacidad por empresa ---")
if "empresa_id" in asesores.columns and "capacidad_diaria" in asesores.columns:
    print(asesores.groupby("empresa_id")["capacidad_diaria"].agg(["count", "sum", "mean"]))

# ── 5. historico_cierres.csv ──────────────────────────────────────────────────

historico = pd.read_csv(f"{RAW}/historico_cierres.csv")
resumen_df(historico, "historico_cierres.csv")

print("\n--- Distribución de desenlaces ---")
print(historico["desenlace"].value_counts())

print("\n--- Tasa de cierre por canal ---")
cierre_canal = historico.groupby("canal")["desenlace"].apply(
    lambda x: (x == "Cerrado").sum() / len(x) * 100
).round(1)
print(cierre_canal)

print("\n--- Tasa de cierre por forma de pago ---")
if "forma_pago_declarada" in historico.columns:
    cierre_pago = historico.groupby("forma_pago_declarada")["desenlace"].apply(
        lambda x: (x == "Cerrado").sum() / len(x) * 100
    ).round(1)
    print(cierre_pago)

print("\n--- Tasa de cierre: manifestó cuota inicial ---")
if "manifesto_cuota_inicial" in historico.columns:
    cierre_cuota = historico.groupby("manifesto_cuota_inicial")["desenlace"].apply(
        lambda x: (x == "Cerrado").sum() / len(x) * 100
    ).round(1)
    print(cierre_cuota)

print("\n--- Tasa de cierre: pidió cita ---")
if "pidio_cita" in historico.columns:
    cierre_cita = historico.groupby("pidio_cita")["desenlace"].apply(
        lambda x: (x == "Cerrado").sum() / len(x) * 100
    ).round(1)
    print(cierre_cita)

print("\n--- Horas al primer contacto vs desenlace ---")
if "horas_primer_contacto" in historico.columns:
    print(historico.groupby("desenlace")["horas_primer_contacto"].agg(["mean", "median"]).round(1))

print("\n\n Exploración completa.")