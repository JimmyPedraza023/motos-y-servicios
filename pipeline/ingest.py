"""
Módulo de ingesta: lee los archivos fuente y los retorna como DataFrames/dict validados.
No hace transformaciones - solo lectura y validación básica de estructura.
"""

import json
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

RAW_DIR = Path("data/raw")

COLUMNAS_REQUERIDAS = {
    "leads": [
        "lead_id", "fecha_registro", "canal", "empresa_id",
        "punto_venta_id", "nombre_cliente", "telefono",
        "modelo_interes_texto", "estado_gestion",
    ],
    "catalogo_motos": ["marca", "linea", "precio_lista"],
    "asesores": ["asesor_id", "empresa_id", "punto_venta_id", "capacidad_diaria_leads"],
    "historico_cierres": [
        "lead_id", "canal", "empresa_id", "desenlace",
        "manifesto_cuota_inicial", "forma_pago_declarada", "pidio_cita",
    ],
}


def _validar_columnas(df: pd.DataFrame, nombre: str) -> None:
    """Verifica que el DataFrame tenga las columnas mínimas requeridas."""
    requeridas = COLUMNAS_REQUERIDAS.get(nombre, [])
    faltantes = [c for c in requeridas if c not in df.columns]
    if faltantes:
        raise ValueError(f"[{nombre}] Columnas faltantes: {faltantes}")


def leer_leads() -> pd.DataFrame:
    path = RAW_DIR / "leads.csv"
    logger.info(f"Leyendo {path}")
    df = pd.read_csv(path, dtype=str)
    _validar_columnas(df, "leads")

    # Eliminar filas con lead_id duplicado — registros idénticos por error del CRM
    # Caso detectado: LD-00011 aparece en filas 12 y 1503 con datos 100% iguales
    duplicados_id = df[df.duplicated(subset=["lead_id"], keep=False)]
    if not duplicados_id.empty:
        ids_afectados = duplicados_id["lead_id"].unique().tolist()
        logger.warning(f"lead_id duplicados en fuente (error CRM): {ids_afectados} → se conserva primera ocurrencia")
        df = df.drop_duplicates(subset=["lead_id"], keep="first")

    logger.info(f"leads.csv: {len(df):,} filas, {len(df.columns)} columnas")
    return df


def leer_conversaciones() -> list[dict]:
    path = RAW_DIR / "conversaciones.json"
    logger.info(f"Leyendo {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("conversaciones.json debe ser un arreglo JSON en la raíz")
    logger.info(f"conversaciones.json: {len(data):,} conversaciones")
    return data


def leer_catalogo() -> pd.DataFrame:
    path = RAW_DIR / "catalogo_motos.csv"
    logger.info(f"Leyendo {path}")
    df = pd.read_csv(path, dtype=str)
    _validar_columnas(df, "catalogo_motos")
    logger.info(f"catalogo_motos.csv: {len(df):,} filas")
    return df


def leer_asesores() -> pd.DataFrame:
    path = RAW_DIR / "asesores.csv"
    logger.info(f"Leyendo {path}")
    df = pd.read_csv(path, dtype=str)
    _validar_columnas(df, "asesores")
    logger.info(f"asesores.csv: {len(df):,} filas")
    return df


def leer_historico() -> pd.DataFrame:
    path = RAW_DIR / "historico_cierres.csv"
    logger.info(f"Leyendo {path}")
    df = pd.read_csv(path, dtype=str)
    _validar_columnas(df, "historico_cierres")
    logger.info(f"historico_cierres.csv: {len(df):,} filas")
    return df


def ingestar_todo() -> dict[str, object]:
    """
    Punto de entrada principal. Retorna todos los insumos listos para
    el siguiente paso del pipeline (normalización).
    """
    logger.info("=== INICIO INGESTA ===")
    resultado = {
        "leads": leer_leads(),
        "conversaciones": leer_conversaciones(),
        "catalogo": leer_catalogo(),
        "asesores": leer_asesores(),
        "historico": leer_historico(),
    }
    logger.info("=== INGESTA COMPLETA ===")
    return resultado


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(levelname)s — %(message)s")
    datos = ingestar_todo()
    for nombre, contenido in datos.items():
        if isinstance(contenido, pd.DataFrame):
            print(f" {nombre}: {len(contenido):,} filas")
        else:
            print(f" {nombre}: {len(contenido):,} registros")