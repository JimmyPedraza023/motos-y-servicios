"""
Módulo de normalización: limpia y estandariza los datos crudos de leads.

Transformaciones aplicadas:
  - Canal: 9 variantes → 3 valores canónicos
  - Estado de gestión: mayúsculas/minúsculas → valor canónico
  - Teléfono: múltiples formatos → E.164 (+57XXXXXXXXXX)
  - Fecha: DD-MM-YYYY / ISO con T / ISO con espacio → ISO 8601
  - Ciudad: múltiples variantes → nombre canónico
  - Modelo de interés: texto libre → match contra catálogo (fuzzy)
  - Email: lowercase y strip
"""

import logging
import re
import unicodedata
from datetime import datetime
from db.client import get_client
import math

import pandas as pd
from rapidfuzz import process, fuzz

logger = logging.getLogger(__name__)


#Mapas de normalización

CANAL_MAP = {
    "whatsapp":       "WhatsApp",
    "meta ads":       "Meta Ads",
    "formulario web": "Formulario Web",
}

ESTADO_MAP = {
    "sin gestión":         "Sin gestión",
    "sin gestion":         "Sin gestión",
    "contactado":          "Contactado",
    "cotización enviada":  "Cotización enviada",
    "cotizacion enviada":  "Cotización enviada",
    "en proceso":          "En proceso",
    "no contesta":         "No contesta",
    "descartado":          "Descartado",
}

CIUDAD_MAP = {
    # Bogotá
    "bogota":     "Bogotá",
    "bogotá":     "Bogotá",
    "bogota dc":  "Bogotá",
    "bogotá dc":  "Bogotá",
    "bogota d.c": "Bogotá",
    "bogotá d.c": "Bogotá",
    # Medellín
    "medellin":   "Medellín",
    "medellín":   "Medellín",
    # Barranquilla
    "barranquilla": "Barranquilla",
    # Cartagena
    "cartagena":  "Cartagena",
    # Santa Marta
    "santa marta": "Santa Marta",
    # Soledad
    "soledad":    "Soledad",
    # Soacha
    "soacha":     "Soacha",
    # Rionegro
    "rio negro":  "Rionegro",
    "rionegro":   "Rionegro",
    # Montería
    "monteria":   "Montería",
    "montería":   "Montería",
    # Bello
    "bello":      "Bello",
    # Itagüí
    "itagui":     "Itagüí",
    "itagüí":     "Itagüí",
}


#Helpers internos 

def _quitar_tildes(texto: str) -> str:
    """Convierte 'Bogotá' → 'Bogota' para comparaciones."""
    return unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode("ascii")


def _clave_normalizar(texto: str) -> str:
    """Strip + lowercase + sin tildes. Para buscar en los mapas."""
    return _quitar_tildes(texto.strip().lower())


#Normalización de canal 

def normalizar_canal(valor: str | None) -> str | None:
    if pd.isna(valor) or valor is None:
        return None
    clave = _clave_normalizar(str(valor))
    return CANAL_MAP.get(clave)   # retorna None si no está en el mapa


#Normalización de estado de gestión 

def normalizar_estado(valor: str | None) -> str | None:
    if pd.isna(valor) or valor is None:
        return None
    clave = _clave_normalizar(str(valor))
    return ESTADO_MAP.get(clave, valor.strip())  # si no está en el mapa, deja el valor limpio


#Normalización de teléfono → E.164 

def normalizar_telefono(valor: str | None) -> str | None:
    """
    Convierte cualquier formato colombiano a E.164 (+57XXXXXXXXXX).
    Acepta: '310 482 4081', '3055411722', '+57 350 2258611', '57-300-123-4567'
    """
    if pd.isna(valor) or valor is None:
        return None

    # Quitar todo lo que no sea dígito o '+'
    limpio = re.sub(r"[^\d+]", "", str(valor).strip())

    # Quitar prefijo internacional si ya viene
    if limpio.startswith("+57"):
        limpio = limpio[3:]
    elif limpio.startswith("57") and len(limpio) == 12:
        limpio = limpio[2:]

    # Validar que queden 10 dígitos colombianos
    if re.fullmatch(r"3\d{9}", limpio):
        return f"+57{limpio}"

    # No se pudo normalizar — lo dejamos como None para marcarlo
    logger.debug(f"Teléfono no normalizable: {valor!r}")
    return None


#Normalización de fechas → ISO 8601

_FORMATOS_FECHA = [
    "%d-%m-%Y",               # 25-08-2026
    "%Y-%m-%dT%H:%M:%S",      # 2026-08-26T14:26:00
    "%Y-%m-%d %H:%M:%S",      # 2026-08-04 14:47:00
    "%Y-%m-%d",               # 2026-08-26
    "%d/%m/%Y",               # 25/08/2026
    "%d/%m/%Y %H:%M:%S",      # 25/08/2026 14:26:00
]

def normalizar_fecha(valor: str | None) -> str | None:
    """Retorna la fecha en formato ISO 8601 (YYYY-MM-DDTHH:MM:SS) o None."""
    if pd.isna(valor) or valor is None or str(valor).strip() == "":
        return None

    texto = str(valor).strip()
    for fmt in _FORMATOS_FECHA:
        try:
            dt = datetime.strptime(texto, fmt)
            return dt.isoformat()
        except ValueError:
            continue

    logger.debug(f"Fecha no parseable: {valor!r}")
    return None


#Normalización de ciudad 

def normalizar_ciudad(valor: str | None) -> str | None:
    if pd.isna(valor) or valor is None:
        return None
    clave = _clave_normalizar(str(valor))
    # Buscar en el mapa exacto primero
    if clave in CIUDAD_MAP:
        return CIUDAD_MAP[clave]
    # Si no está, retornar el valor con strip y title case como fallback
    return str(valor).strip().title()


#Normalización de email 

def normalizar_email(valor: str | None) -> str | None:
    if pd.isna(valor) or valor is None:
        return None
    limpio = str(valor).strip().lower()
    # Validación básica de formato
    if "@" in limpio and "." in limpio.split("@")[-1]:
        return limpio
    return None


#Mapeo de modelo de interés al catálogo 

def construir_indice_catalogo(df_catalogo: pd.DataFrame) -> dict[str, str]:
    """
    Construye un diccionario {texto_busqueda: sku} con todas
    las variantes de nombre posibles para cada moto del catálogo.
    """
    indice = {}
    for _, row in df_catalogo.iterrows():
        sku = str(row.get("sku", "")).strip()
        marca = str(row.get("marca", "")).strip()
        linea = str(row.get("linea", "")).strip()
        cilindraje = str(row.get("cilindraje", "")).strip()

        # Variantes del nombre — de más específica a más general
        variantes = [
            f"{marca} {linea}",            # "Honda CB 125F Twister"
            f"{marca} {linea} {cilindraje}", # "Honda CB 125F Twister 125"
            linea,                          # "CB 125F Twister"
            f"{linea} {cilindraje}",        # "CB 125F Twister 125"
        ]
        for v in variantes:
            clave = _clave_normalizar(v)
            if clave:
                indice[clave] = sku   # ← sku, no referencia_id

    return indice


def mapear_modelo(texto: str | None, indice_catalogo: dict[str, str],
                  umbral: int = 70) -> str | None:
    """
    Mapea texto libre de modelo al SKU del catálogo usando fuzzy matching.
    Retorna el SKU si la similitud supera el umbral, o None.
    """
    if pd.isna(texto) or texto is None or str(texto).strip() == "":
        return None

    texto_norm = _clave_normalizar(str(texto))
    candidatos = list(indice_catalogo.keys())

    resultado = process.extractOne(
        texto_norm,
        candidatos,
        scorer=fuzz.token_sort_ratio,
        score_cutoff=umbral,
    )

    if resultado:
        mejor_clave, score, _ = resultado
        sku = indice_catalogo[mejor_clave]
        logger.debug(f"Modelo '{texto}' → '{sku}' (score={score})")
        return sku

    logger.debug(f"Modelo sin match: '{texto}'")
    return None

#Función principal 

def normalizar_leads(df: pd.DataFrame, df_catalogo: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica todas las transformaciones al DataFrame de leads.
    Retorna un nuevo DataFrame normalizado, sin modificar el original.
    """
    logger.info(f"Normalizando {len(df):,} leads...")
    resultado = df.copy()

    # 1. Canal
    resultado["canal"] = resultado["canal"].apply(normalizar_canal)
    nulos_canal = resultado["canal"].isna().sum()
    logger.info(f"  Canal: {nulos_canal} valores no normalizables → None")

    # 2. Estado de gestión
    resultado["estado_gestion"] = resultado["estado_gestion"].apply(normalizar_estado)

    # 3. Teléfono → E.164
    resultado["telefono"] = resultado["telefono"].apply(normalizar_telefono)
    nulos_tel = resultado["telefono"].isna().sum()
    logger.info(f"  Teléfono: {nulos_tel} valores no normalizables → None")

    # 4. Fechas
    resultado["fecha_registro"] = resultado["fecha_registro"].apply(normalizar_fecha)
    resultado["fecha_primer_contacto"] = resultado["fecha_primer_contacto"].apply(normalizar_fecha)

    # 5. Ciudad
    resultado["ciudad"] = resultado["ciudad"].apply(normalizar_ciudad)

    # 6. Email
    resultado["email"] = resultado["email"].apply(normalizar_email)

    # 7. Modelo → referencia_id del catálogo
    indice = construir_indice_catalogo(df_catalogo)
    resultado["sku"] = resultado["modelo_interes_texto"].apply(   # ← sku, no referencia_id
        lambda x: mapear_modelo(x, indice)
    )
    sin_match = resultado["sku"].isna().sum()
    logger.info(f"  Modelo de interés: {sin_match} sin match en catálogo")

    # 8. Columnas de texto: strip general
    for col in ["nombre_cliente", "campania", "empresa_id", "punto_venta_id"]:
        if col in resultado.columns:
            resultado[col] = resultado[col].apply(
                lambda x: str(x).strip() if pd.notna(x) else None
            )

    logger.info("Normalización completa.")
    return resultado


def normalizar_asesores(df: pd.DataFrame) -> pd.DataFrame:
    """Limpieza básica del DataFrame de asesores."""
    resultado = df.copy()

    # empresa_id / punto_venta_id: strip — deben matchear exacto contra leads
    for col in ["empresa_id", "punto_venta_id"]:
        if col in resultado.columns:
            resultado[col] = resultado[col].apply(
                lambda x: str(x).strip() if pd.notna(x) else None
            )
   
    # activo: 'SI'/'NO' → bool
    if "activo" in resultado.columns:
        resultado["activo"] = resultado["activo"].str.strip().str.upper().map(
            {"SI": True, "NO": False, "TRUE": True, "FALSE": False}
        )
    # capacidad_diaria_leads → int
    if "capacidad_diaria_leads" in resultado.columns:
        resultado["capacidad_diaria_leads"] = pd.to_numeric(
            resultado["capacidad_diaria_leads"], errors="coerce"
        ).fillna(10).astype(int)
    return resultado


def normalizar_historico(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza el histórico para que sea compatible con el análisis de scoring."""
    resultado = df.copy()

    # Canal — mismas variantes que leads
    resultado["canal"] = resultado["canal"].apply(normalizar_canal)

    # Booleanos en texto → bool
    bool_map = {"SI": True, "NO": False, "NO_INFORMA": None}
    for col in ["manifesto_cuota_inicial", "pidio_cita"]:
        if col in resultado.columns:
            resultado[col] = resultado[col].str.strip().str.upper().map(bool_map)

    # Numérico
    resultado["horas_al_primer_contacto"] = pd.to_numeric(
        resultado["horas_al_primer_contacto"], errors="coerce"
    )
    resultado["precio_lista"] = pd.to_numeric(
        resultado["precio_lista"], errors="coerce"
    )

    return resultado


def persist_leads(df_leads: pd.DataFrame, run_id: str) -> None:
    from db.client import get_client
    db = get_client()

    COLUMNAS_DB = [
        "lead_id", "empresa_id", "punto_venta_id", "nombre_cliente",
        "telefono", "email", "ciudad", "canal", "campania",
        "fecha_registro", "modelo_interes_texto", "referencia_id",
        "estado_gestion", "fecha_primer_contacto", "es_duplicado",
        "lead_id_principal",
    ]

    cols_presentes = [c for c in COLUMNAS_DB if c in df_leads.columns]
    df_db = df_leads[cols_presentes].copy()
    df_db["pipeline_run_id"] = run_id

    # Filtrar leads que violarían NOT NULL constraints
    antes = len(df_db)
    df_db = df_db[df_db["canal"].notna()]
    descartados = antes - len(df_db)
    if descartados > 0:
        logger.warning(
            f"{descartados} leads descartados por canal nulo (datos inválidos)"
        )

    records = [
        {k: (None if pd.isna(v) else v) for k, v in row.items()}
        for row in df_db.to_dict(orient="records")
    ]

    batch_size = 500
    for i in range(0, len(records), batch_size):
        db.table("leads").upsert(
            records[i:i + batch_size], on_conflict="lead_id"
        ).execute()

    logger.info(f"{len(records)} leads persistidos en Supabase")


def persist_conversaciones(conversaciones: list[dict]) -> None:
    from db.client import get_client
    db = get_client()

    # Obtener los lead_ids que realmente existen en la tabla leads
    resultado = db.table("leads").select("lead_id").execute()
    leads_existentes = {row["lead_id"] for row in resultado.data}

    records = []
    huerfanas = 0
    for conv in conversaciones:
        lead_id = conv.get("lead_id")

        # Descartar conversaciones cuyo lead no existe en la DB
        if lead_id not in leads_existentes:
            huerfanas += 1
            continue

        mensajes = conv.get("mensajes", [])
        records.append({
            "conversacion_id": conv.get("conversacion_id"),
            "lead_id":         lead_id,
            "canal":           conv.get("canal"),
            "fecha_inicio":    conv.get("fecha_inicio"),
            "total_mensajes":  len(mensajes),
            "raw_json":        conv,
        })

    if huerfanas > 0:
        logger.warning(
            f"{huerfanas} conversaciones descartadas por lead_id inexistente"
        )

    batch_size = 500
    for i in range(0, len(records), batch_size):
        db.table("conversaciones").upsert(
            records[i:i + batch_size], on_conflict="conversacion_id"
        ).execute()

    logger.info(f"{len(records)} conversaciones persistidas en Supabase")

#Ejecución directa para prueba 

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s — %(levelname)s — %(message)s"
    )
    from pipeline.ingest import ingestar_todo

    datos = ingestar_todo()
    leads_norm = normalizar_leads(datos["leads"], datos["catalogo"])
    asesores_norm = normalizar_asesores(datos["asesores"])
    historico_norm = normalizar_historico(datos["historico"])

    print("\n=== VERIFICACIÓN POST-NORMALIZACIÓN ===")

    print("\n--- Canal ---")
    print(leads_norm["canal"].value_counts(dropna=False))

    print("\n--- Estado de gestión ---")
    print(leads_norm["estado_gestion"].value_counts(dropna=False))

    print("\n--- Teléfono (muestra) ---")
    print(leads_norm["telefono"].dropna().head(5).tolist())

    print("\n--- Fecha registro (muestra) ---")
    print(leads_norm["fecha_registro"].dropna().head(5).tolist())

    print("\n--- Ciudad (top 10) ---")
    print(leads_norm["ciudad"].value_counts(dropna=False).head(10))

    print("\n--- Modelo → SKU (muestra) ---")
    muestra = leads_norm[["modelo_interes_texto", "sku"]].dropna(
        subset=["modelo_interes_texto"]
    ).head(15)
    print(muestra.to_string())

    # Ver cuántos sí hicieron match
    con_match = leads_norm["sku"].notna().sum()
    sin_match = leads_norm["sku"].isna().sum()
    print(f"\nCon match: {con_match} | Sin match: {sin_match}")

    print("\n--- Asesores activos ---")
    print(asesores_norm["activo"].value_counts(dropna=False))

    print("\n--- Histórico: canal normalizado ---")
    print(historico_norm["canal"].value_counts(dropna=False))

    print("\nNormalización verificada.")