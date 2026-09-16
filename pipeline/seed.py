# pipeline/seed.py
"""
Carga inicial de datos maestros en Supabase.
Debe ejecutarse UNA VEZ antes del primer run del pipeline.
Orden obligatorio por FKs:
    empresas → puntos_venta → catalogo_motos → asesores
"""
import logging
import pandas as pd
from db.client import get_client

logger = logging.getLogger("seed")


def _limpiar(df: pd.DataFrame) -> list[dict]:
    """Convierte DataFrame a lista de dicts eliminando NaN → None."""
    return [
        {k: (None if pd.isna(v) else v) for k, v in row.items()}
        for row in df.to_dict(orient="records")
    ]


def seed_empresas(df_leads: pd.DataFrame) -> None:
    """Deriva las empresas únicas desde leads normalizados."""
    db = get_client()

    empresas = (
        df_leads[["empresa_id"]]
        .drop_duplicates()
        .dropna(subset=["empresa_id"])
        .assign(nombre=lambda x: x["empresa_id"], activa=True)
    )

    db.table("empresas").upsert(
        _limpiar(empresas), on_conflict="empresa_id"
    ).execute()

    logger.info(f"{len(empresas)} empresas cargadas")


def seed_puntos_venta(df_leads: pd.DataFrame) -> None:
    db = get_client()

    puntos = (
        df_leads[["punto_venta_id", "empresa_id", "ciudad"]]
        .drop_duplicates(subset=["punto_venta_id"])
        .dropna(subset=["punto_venta_id", "empresa_id"])
        .assign(nombre=lambda x: x["punto_venta_id"], activo=True)
    )

    # ── DIAGNÓSTICO — quitar después de resolver ──────────────────
    print("\n=== DIAGNÓSTICO puntos_venta ===")
    print(puntos.dtypes)
    print(puntos.head(5).to_string())
    for col in puntos.columns:
        nans = puntos[col].isna().sum()
        if nans > 0:
            print(f"  ⚠ {col}: {nans} NaN")
    print("================================\n")
    # ─────────────────────────────────────────────────────────────

    records = [
        {k: (None if pd.isna(v) else v) for k, v in row.items()}
        for row in puntos.to_dict(orient="records")
    ]

    db.table("puntos_venta").upsert(
        records, on_conflict="punto_venta_id"
    ).execute()

    logger.info(f"{len(puntos)} puntos de venta cargados")


def seed_catalogo(df_catalogo: pd.DataFrame) -> None:
    db = get_client()

    df_db = df_catalogo.rename(columns={
        "sku":        "referencia_id",
        "cilindraje": "cilindraje_cc",
    })[[
        "referencia_id",
        "marca",
        "linea",
        "cilindraje_cc",
        "segmento",
        "precio_lista",
    ]].copy()

    # unidades_disponibles viene como str — convertir a numérico primero
    if "unidades_disponibles" in df_catalogo.columns:
        unidades = pd.to_numeric(
            df_catalogo["unidades_disponibles"], errors="coerce"
        ).fillna(0)
        df_db["disponible"] = unidades > 0
    else:
        df_db["disponible"] = True  # default si no existe la columna

    records = [
        {k: (None if pd.isna(v) else v) for k, v in row.items()}
        for row in df_db.to_dict(orient="records")
    ]

    db.table("catalogo_motos").upsert(
        records, on_conflict="referencia_id"
    ).execute()

    logger.info(f"{len(df_db)} referencias de catálogo cargadas")


def seed_asesores(df_asesores: pd.DataFrame) -> None:
    """Carga los asesores mapeando columnas del CSV al schema."""
    db = get_client()

    # Mapeo CSV → schema (fecha_ingreso no tiene columna en schema, se omite)
    df_db = df_asesores.rename(columns={
        "capacidad_diaria_leads": "capacidad_diaria",
    })[[
        "asesor_id",
        "empresa_id",
        "punto_venta_id",
        "nombre",
        "capacidad_diaria",
        "activo",
    ]].copy()

    db.table("asesores").upsert(
        _limpiar(df_db), on_conflict="asesor_id"
    ).execute()

    logger.info(f"{len(df_db)} asesores cargados")


def run_seed() -> None:
    """Ejecuta la carga completa de datos maestros en orden."""
    from pipeline.ingest import ingestar_todo
    from pipeline.normalize import normalizar_leads, normalizar_asesores

    logger.info("Iniciando seed de datos maestros...")

    datos = ingestar_todo()
    leads_norm    = normalizar_leads(datos["leads"], datos["catalogo"])
    asesores_norm = normalizar_asesores(datos["asesores"])

    # Orden estricto por dependencias de FK
    seed_empresas(leads_norm)
    seed_puntos_venta(leads_norm)
    seed_catalogo(datos["catalogo"])  # catálogo crudo, no normalizado
    seed_asesores(asesores_norm)

    logger.info("Seed completado — datos maestros listos en Supabase")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s — %(levelname)s — %(message)s"
    )
    run_seed()