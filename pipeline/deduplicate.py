"""
Módulo de deduplicación: detecta leads que son la misma persona
contactando por canales distintos o en momentos diferentes.

Estrategia en dos pasos:
  1. Match exacto por teléfono normalizado (E.164) — mismo número = misma persona
  2. Match fuzzy por nombre dentro de la misma empresa — para casos sin teléfono

Para cada grupo de duplicados se elige un lead_id principal (el más antiguo
o el de mayor calidad de datos) y los demás se marcan como duplicados.
"""

import logging
from itertools import combinations
from db.client import get_client

import pandas as pd
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

UMBRAL_NOMBRE_FUZZY = 88  # similitud mínima para considerar mismo cliente por nombre


#Paso 1: duplicados por teléfono exacto 

def _detectar_duplicados_telefono(df: pd.DataFrame) -> dict[str, str]:
    """
    Retorna un dict {lead_id_duplicado: lead_id_principal} para todos
    los leads que comparten el mismo teléfono normalizado.
    Solo compara dentro de la misma empresa (empresa_id).
    """
    mapa = {}  # lead_id → lead_id_principal

    # Solo leads con teléfono válido
    con_tel = df[df["telefono"].notna()].copy()

    # Agrupar por empresa + teléfono
    grupos = con_tel.groupby(["empresa_id", "telefono"])

    for (empresa, telefono), grupo in grupos:
        if len(grupo) < 2:
            continue  # no hay duplicado

        # Ordenar: primero el más antiguo, o el que tiene más datos completos
        grupo_ord = _ordenar_por_calidad(grupo)
        lead_principal = grupo_ord.iloc[0]["lead_id"]

        for _, row in grupo_ord.iloc[1:].iterrows():
            mapa[row["lead_id"]] = lead_principal
            logger.debug(
                f"Duplicado por teléfono: {row['lead_id']} → {lead_principal} "
                f"(tel={telefono}, empresa={empresa})"
            )

    logger.info(f"Duplicados por teléfono exacto: {len(mapa)}")
    return mapa


#Paso 2: duplicados por nombre fuzzy 

def _detectar_duplicados_nombre(df: pd.DataFrame, ya_duplicados: set[str]) -> dict[str, str]:
    """
    Dentro de los leads que NO tienen teléfono (o cuyo teléfono no matcheó),
    busca pares con nombre muy similar dentro de la misma empresa y ciudad.
    """
    mapa = {}

    # Solo leads sin teléfono y que aún no son duplicados confirmados
    sin_tel = df[
        df["telefono"].isna() &
        ~df["lead_id"].isin(ya_duplicados)
    ].copy()

    if sin_tel.empty:
        logger.info("No hay leads sin teléfono para deduplicar por nombre.")
        return mapa

    # Comparar pares dentro de empresa + ciudad
    grupos = sin_tel.groupby(["empresa_id", "ciudad"], dropna=False)

    for (empresa, ciudad), grupo in grupos:
        if len(grupo) < 2:
            continue

        leads_lista = grupo.to_dict("records")

        for a, b in combinations(leads_lista, 2):
            nombre_a = str(a.get("nombre_cliente") or "")
            nombre_b = str(b.get("nombre_cliente") or "")

            if not nombre_a or not nombre_b:
                continue

            score = fuzz.token_sort_ratio(nombre_a.lower(), nombre_b.lower())

            if score >= UMBRAL_NOMBRE_FUZZY:
                # Determinar cuál es el principal
                par_df = pd.DataFrame([a, b])
                par_ord = _ordenar_por_calidad(par_df)
                principal = par_ord.iloc[0]["lead_id"]
                duplicado = par_ord.iloc[1]["lead_id"]

                if duplicado not in mapa:
                    mapa[duplicado] = principal
                    logger.debug(
                        f"Duplicado por nombre: '{nombre_a}' ~ '{nombre_b}' "
                        f"(score={score}, empresa={empresa})"
                    )

    logger.info(f"Duplicados por nombre fuzzy: {len(mapa)}")
    return mapa


#Criterio de calidad para elegir el lead principal 

def _ordenar_por_calidad(grupo: pd.DataFrame) -> pd.DataFrame:
    """
    Ordena un grupo de duplicados para poner primero el lead de mayor calidad.
    Criterios (en orden de prioridad):
      1. Tiene email (más datos)
      2. Canal WhatsApp (más información en conversación)
      3. Fecha de registro más antigua (el primero en contactar)
    """
    def puntaje_calidad(row):
        pts = 0
        if pd.notna(row.get("email")):
            pts += 10
        if row.get("canal") == "WhatsApp":
            pts += 5
        # Fecha más antigua = mejor (invertimos para que quede primero)
        fecha = row.get("fecha_registro")
        if pd.notna(fecha):
            pts += 1  # cualquier fecha es mejor que nada
        return pts

    grupo = grupo.copy()
    grupo["_calidad"] = grupo.apply(puntaje_calidad, axis=1)

    return grupo.sort_values(
        ["_calidad", "fecha_registro"],
        ascending=[False, True]
    ).drop(columns=["_calidad"])


#Función principal 

def deduplicar(df: pd.DataFrame) -> pd.DataFrame:
    """
    Recibe el DataFrame normalizado y retorna uno nuevo con dos columnas añadidas:
      - es_duplicado: bool
      - lead_id_principal: str (apunta al lead canónico; para el principal apunta a sí mismo)

    Solo los leads donde es_duplicado=False deben entrar al pipeline de scoring.
    """
    logger.info(f"Iniciando deduplicación sobre {len(df):,} leads...")

    resultado = df.copy()
    resultado["es_duplicado"] = False
    resultado["lead_id_principal"] = resultado["lead_id"]

    # Paso 1 — teléfono exacto
    mapa_tel = _detectar_duplicados_telefono(resultado)

    # Paso 2 — nombre fuzzy (solo sobre los que no se resolvieron en paso 1)
    mapa_nombre = _detectar_duplicados_nombre(resultado, ya_duplicados=set(mapa_tel.keys()))

    # Combinar mapas (teléfono tiene prioridad)
    mapa_total = {**mapa_nombre, **mapa_tel}

    # Aplicar al DataFrame
    for lead_dup, lead_principal in mapa_total.items():
        mask = resultado["lead_id"] == lead_dup
        resultado.loc[mask, "es_duplicado"] = True
        resultado.loc[mask, "lead_id_principal"] = lead_principal

    # Resumen
    total_dup = resultado["es_duplicado"].sum()
    total_unicos = (~resultado["es_duplicado"]).sum()
    logger.info(f"Resultado deduplicación:")
    logger.info(f"  Leads únicos (activos para pipeline): {total_unicos:,}")
    logger.info(f"  Leads duplicados (excluidos):         {total_dup:,}")
    logger.info(f"  Total original:                       {len(resultado):,}")

    return resultado


def resumen_duplicados(df_dedup: pd.DataFrame) -> None:
    """Imprime un resumen de los duplicados encontrados por empresa y canal."""
    dup = df_dedup[df_dedup["es_duplicado"]]

    print(f"\n=== RESUMEN DE DUPLICADOS ===")
    print(f"Total duplicados: {len(dup)}")

    if len(dup) == 0:
        print("No se encontraron duplicados.")
        return

    print(f"\nDuplicados por empresa:")
    print(dup["empresa_id"].value_counts().to_string())

    print(f"\nDuplicados por canal:")
    print(dup["canal"].value_counts(dropna=False).to_string())

    print(f"\nMuestra de pares duplicados:")
    muestra = df_dedup[
        df_dedup["lead_id"].isin(dup["lead_id_principal"].unique())
    ][["lead_id", "nombre_cliente", "telefono", "canal", "empresa_id"]].head(5)
    print(muestra.to_string())


def persist_duplicates(df_leads: pd.DataFrame) -> None:
    """Actualiza los flags de deduplicación en la tabla leads de Supabase."""
    from db.client import get_client
    db = get_client()

    # Filtrar solo los duplicados
    duplicados = df_leads[df_leads["es_duplicado"] == True][[
        "lead_id", "lead_id_principal"
    ]]

    if duplicados.empty:
        logger.info("Sin duplicados que persistir")
        return

    # Actualizar cada duplicado individualmente
    actualizados = 0
    for _, row in duplicados.iterrows():
        db.table("leads").update({
            "es_duplicado":      True,
            "lead_id_principal": row["lead_id_principal"]
        }).eq("lead_id", row["lead_id"]).execute()
        actualizados += 1

    logger.info(f"{actualizados} leads marcados como duplicados en Supabase")

#Ejecución directa para prueba 

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s — %(levelname)s — %(message)s"
    )
    from pipeline.ingest import ingestar_todo
    from pipeline.normalize import normalizar_leads

    datos = ingestar_todo()
    leads_norm = normalizar_leads(datos["leads"], datos["catalogo"])
    leads_dedup = deduplicar(leads_norm)

    resumen_duplicados(leads_dedup)

    print(f"\n=== VERIFICACIÓN CRUZADA DE UN DUPLICADO ===")
    dup_muestra = leads_dedup[leads_dedup["es_duplicado"]].head(3)
    for _, row in dup_muestra.iterrows():
        principal = leads_dedup[leads_dedup["lead_id"] == row["lead_id_principal"]].iloc[0]
        print(f"\nDuplicado : [{row['lead_id']}] {row['nombre_cliente']} | {row['telefono']} | {row['canal']}")
        print(f"Principal : [{principal['lead_id']}] {principal['nombre_cliente']} | {principal['telefono']} | {principal['canal']}")