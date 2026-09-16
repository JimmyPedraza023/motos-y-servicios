"""
Módulo de asignación: distribuye los leads priorizados entre los asesores
disponibles respetando su capacidad diaria y punto de venta.

Estrategia:
  - Solo se asignan leads activos (no duplicados) con temperatura Caliente o Tibio.
  - Los leads Fríos quedan en cola sin asignar — no consumen capacidad del asesor.
  - Los leads se procesan globalmente en orden de score desc (no por punto de venta).
  - Si un punto de venta tiene más leads que capacidad total de sus asesores,
    los excedentes quedan sin asignar (campo asesor_id = None).
  - La asignación respeta la separación por empresa: un asesor de EMP-01
    nunca recibe leads de EMP-02 o EMP-03.
  - Entre asesores candidatos, se elige greedy al de mayor capacidad restante
    (no round-robin real) — esto tiende a equilibrar la carga sin garantizar
    una distribución estrictamente uniforme.
"""

import logging
from datetime import date
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Temperaturas que se asignan a asesores
TEMPERATURAS_ASIGNABLES = {"Caliente", "Tibio"}

_COLUMNAS_ASIGNACION_DB = [
    "lead_id",
    "asesor_id",
    "fecha_asignacion",
    "orden_prioridad",
]

# ── Preparación de asesores ───────────────────────────────────────────────────

def _preparar_asesores(df_asesores: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza el DataFrame de asesores y agrega columna de capacidad restante.
    Solo incluye asesores activos.
    """
    df = df_asesores.copy()

    # Normalizar columna activo si viene como string
    if df["activo"].dtype == object:
        df["activo"] = df["activo"].str.strip().str.upper().map(
            {"SI": True, "NO": False, "TRUE": True, "FALSE": False}
        )

    # Solo asesores activos
    df = df[df["activo"] == True].copy()

    # Capacidad diaria como entero
    df["capacidad_diaria_leads"] = pd.to_numeric(
        df["capacidad_diaria_leads"], errors="coerce"
    ).fillna(10).astype(int)

    # Capacidad restante (inicia igual a la capacidad diaria)
    df["capacidad_restante"] = df["capacidad_diaria_leads"]

    logger.info(
        f"Asesores activos: {len(df)} | "
        f"Capacidad total del día: {df['capacidad_diaria_leads'].sum()} leads"
    )
    return df


def persist_asignaciones(df_resultado: pd.DataFrame, run_id: str) -> None:
    from db.client import get_client
    db = get_client()

    _COLUMNAS_ASIGNACION_DB = [
        "lead_id", "asesor_id", "fecha_asignacion", "orden_prioridad"
    ]

    df_asig = df_resultado[
        df_resultado["asignado"] == True
    ][_COLUMNAS_ASIGNACION_DB].copy()

    df_asig["pipeline_run_id"] = run_id
    df_asig["atendido"] = False

    # orden_prioridad viene como float por mezcla con NaN — forzar a int
    df_asig["orden_prioridad"] = df_asig["orden_prioridad"].astype(int)

    records = [
        {k: (None if pd.isna(v) else v) for k, v in row.items()}
        for row in df_asig.to_dict(orient="records")
    ]

    if records:
        db.table("lead_asignaciones").insert(records).execute()

    logger.info(f"{len(records)} asignaciones persistidas en Supabase")


# ── Asignación principal ──────────────────────────────────────────────────────

def asignar_leads(
    df_scored: pd.DataFrame,
    df_asesores: pd.DataFrame,
    fecha_asignacion: date = None,
) -> pd.DataFrame:
    """
    Asigna cada lead elegible al asesor disponible más adecuado.

    Criterios de asignación:
      1. Empresa: el asesor debe pertenecer a la misma empresa que el lead.
      2. Punto de venta: preferencia por asesores del mismo punto de venta.
         Si no hay capacidad en el punto de venta, busca en la misma empresa.
      3. Capacidad: el asesor debe tener capacidad restante > 0.
      4. Orden: leads ordenados por score desc dentro de cada punto de venta.

    Args:
        df_scored:         DataFrame con scores calculados (salida de score.py)
        df_asesores:       DataFrame de asesores (salida de ingest.py)
        fecha_asignacion:  fecha del día (default: hoy)

    Returns:
        DataFrame con columnas de asignación añadidas.
    """
    if fecha_asignacion is None:
        fecha_asignacion = date.today()

    df_asesores_prep = _preparar_asesores(df_asesores)

    # Índice mutable de capacidad restante por asesor
    capacidad: dict[str, int] = dict(
        zip(
            df_asesores_prep["asesor_id"],
            df_asesores_prep["capacidad_restante"],
        )
    )

    # Metadata de cada asesor para búsqueda rápida
    asesor_info: dict[str, dict] = {
        row["asesor_id"]: {
            "empresa_id":     row["empresa_id"],
            "punto_venta_id": row["punto_venta_id"],
        }
        for _, row in df_asesores_prep.iterrows()
    }

    # Índice: empresa → punto_venta → lista de asesor_ids
    indice_asesores: dict[str, dict[str, list[str]]] = {}
    for asesor_id, info in asesor_info.items():
        emp = info["empresa_id"]
        pv  = info["punto_venta_id"]
        indice_asesores.setdefault(emp, {}).setdefault(pv, []).append(asesor_id)

    # Solo leads elegibles (no duplicados, temperatura asignable)
    elegibles = df_scored[
        (~df_scored["es_duplicado"]) &
        (df_scored["temperatura"].isin(TEMPERATURAS_ASIGNABLES))
    ].copy()

    # Ordenar por score desc para asignar primero los mejores leads
    elegibles = elegibles.sort_values("score_total", ascending=False)

    logger.info(
        f"Leads elegibles para asignación: {len(elegibles):,} "
        f"({TEMPERATURAS_ASIGNABLES})"
    )

    # Resultado de asignaciones
    asignaciones = []

    for orden, (_, lead) in enumerate(elegibles.iterrows(), start=1):
        lead_id    = str(lead["lead_id"])
        empresa_id = str(lead.get("empresa_id", ""))
        pv_id      = str(lead.get("punto_venta_id", ""))

        asesor_asignado = _buscar_asesor(
            empresa_id, pv_id, indice_asesores, capacidad
        )

        if asesor_asignado:
            capacidad[asesor_asignado] -= 1

        asignaciones.append({
            "lead_id":          lead_id,
            "asesor_id":        asesor_asignado,
            "fecha_asignacion": fecha_asignacion.isoformat(),
            "orden_prioridad":  orden,
            "asignado":         asesor_asignado is not None,
        })

    df_asignaciones = pd.DataFrame(asignaciones)

    # Merge con el DataFrame scored para retornar todo junto
    df_resultado = df_scored.merge(df_asignaciones, on="lead_id", how="left")

    # Leads Fríos: marcar explícitamente como no asignados
    mask_frios = df_resultado["temperatura"] == "Frio"
    df_resultado.loc[mask_frios, "asignado"] = False
    df_resultado.loc[mask_frios, "asesor_id"] = None

    # ── Resumen ───────────────────────────────────────────────────────────────
    asignados     = df_asignaciones["asignado"].sum()
    sin_asesor    = (~df_asignaciones["asignado"]).sum()
    frios_total   = mask_frios.sum()

    logger.info("=== ASIGNACIÓN COMPLETA ===")
    logger.info(f"  Leads elegibles       : {len(elegibles):,}")
    logger.info(f"  Asignados a asesor    : {asignados:,}")
    logger.info(f"  Sin asesor disponible : {sin_asesor:,}")
    logger.info(f"  Leads Fríos (en cola) : {frios_total:,}")
    logger.info(
        f"  Capacidad total usada : "
        f"{sum(df_asesores_prep['capacidad_diaria_leads']) - sum(capacidad.values()):,} "
        f"/ {sum(df_asesores_prep['capacidad_diaria_leads']):,}"
    )

    return df_resultado


def _buscar_asesor(
    empresa_id: str,
    punto_venta_id: str,
    indice: dict[str, dict[str, list[str]]],
    capacidad: dict[str, int],
) -> Optional[str]:
    """
    Busca el asesor disponible más adecuado para un lead.

    Prioridad de búsqueda:
      1. Mismo punto de venta + misma empresa
      2. Misma empresa (cualquier punto de venta)
      3. None si no hay capacidad disponible

    Dentro de cada grupo elige, de forma greedy, el asesor con mayor
    capacidad restante. En empates, max() devuelve el primero en orden
    de aparición en el DataFrame de asesores — no hay desempate explícito
    adicional.
    """
    empresa_asesores = indice.get(empresa_id, {})

    # 1. Mismo punto de venta
    candidatos_pv = [
        a for a in empresa_asesores.get(punto_venta_id, [])
        if capacidad.get(a, 0) > 0
    ]
    if candidatos_pv:
        return max(candidatos_pv, key=lambda a: capacidad[a])

    # 2. Misma empresa, cualquier punto de venta
    todos_empresa = [
        a for asesores_pv in empresa_asesores.values()
        for a in asesores_pv
        if capacidad.get(a, 0) > 0
    ]
    if todos_empresa:
        return max(todos_empresa, key=lambda a: capacidad[a])

    # 3. Sin capacidad disponible
    return None


# ── Resumen de asignación por asesor ─────────────────────────────────────────

def resumen_asignacion(
    df_resultado: pd.DataFrame,
    df_asesores: pd.DataFrame,
) -> None:
    """Imprime un resumen de la asignación por asesor para validación."""
    print("\n=== RESUMEN DE ASIGNACIÓN ===")

    asignados = df_resultado[df_resultado["asignado"] == True]

    print(f"\nLeads asignados: {len(asignados):,}")
    print(f"Leads sin asignar: {(df_resultado['asignado'] == False).sum():,}")

    if "asesor_id" in asignados.columns and len(asignados) > 0:
        print("\n--- Carga por asesor (top 10) ---")
        carga = (
            asignados.groupby("asesor_id")
            .agg(
                leads_asignados=("lead_id", "count"),
                score_promedio=("score_total", "mean"),
                calientes=("temperatura", lambda x: (x == "Caliente").sum()),
            )
            .sort_values("leads_asignados", ascending=False)
            .round(1)
            .head(10)
        )
        # Agregar nombre del asesor si está disponible
        if "nombre" in df_asesores.columns:
            carga = carga.merge(
                df_asesores[["asesor_id", "nombre"]],
                on="asesor_id",
                how="left",
            )
        print(carga.to_string())

    print("\n--- Asignación por empresa ---")
    if "empresa_id" in asignados.columns:
        print(
            asignados.groupby("empresa_id")["lead_id"]
            .count()
            .rename("leads_asignados")
        )

    print("\n--- Muestra: mis leads de hoy (primer asesor) ---")
    if "asesor_id" in asignados.columns and len(asignados) > 0:
        primer_asesor = asignados["asesor_id"].dropna().iloc[0]
        mis_leads = asignados[asignados["asesor_id"] == primer_asesor][
            ["lead_id", "nombre_cliente", "canal", "score_total",
             "temperatura", "orden_prioridad", "explicacion"]
        ].head(5)
        print(f"Asesor: {primer_asesor}")
        print(mis_leads.to_string())


# ── Ejecución directa para prueba ─────────────────────────────────────────────

if __name__ == "__main__":
    import json
    from pathlib import Path

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s — %(levelname)s — %(message)s",
    )

    from pipeline.ingest import ingestar_todo
    from pipeline.normalize import normalizar_leads, normalizar_asesores
    from pipeline.deduplicate import deduplicar
    from pipeline.score import calcular_scores

    # Cargar extracciones desde checkpoint
    checkpoint = Path("data/processed/extracciones.json")
    if checkpoint.exists():
        with open(checkpoint, "r", encoding="utf-8") as f:
            extracciones = json.load(f)
        print(f"Extracciones cargadas: {len(extracciones)}")
    else:
        extracciones = []
        print("Sin checkpoint — asignación sin datos de IA")

    datos          = ingestar_todo()
    leads_norm     = normalizar_leads(datos["leads"], datos["catalogo"])
    leads_dedup    = deduplicar(leads_norm)
    df_scored      = calcular_scores(leads_dedup, extracciones)
    asesores_norm  = normalizar_asesores(datos["asesores"])

    df_resultado   = asignar_leads(df_scored, asesores_norm)
    resumen_asignacion(df_resultado, asesores_norm)

    print("\nAsignación completa.")