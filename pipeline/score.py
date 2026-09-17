"""
Módulo de scoring: asigna a cada lead un score de prioridad (0-100)
y una temperatura (Caliente / Tibio / Frio).

Estrategia: reglas ponderadas calibradas con historico_cierres.csv.
No se entrena un modelo desde cero — se usan las tasas de cierre reales
del histórico como pesos. Esto hace el scoring explicable y defendible.

Pesos derivados del histórico (tasas de cierre reales):
  Canal:
    WhatsApp       → 9.5%  (mayor tasa)
    Formulario Web → 9.0%
    Meta Ads       → 8.1%  (menor tasa)

  Cuota inicial declarada:
    Sí             → 10.9% (mayor tasa)
    No             →  8.1%
    No informa     →  7.0%

  Pidió cita/cotización:
    Sí             → 11.0% (mayor tasa)
    No             →  8.1%

  Forma de pago:
    Contado        → 11.0%
    Leasing        →  9.0% (estimado)
    No informa     →  8.0%
    Crédito        →  7.7% (menor tasa)

  Tiempo sin contacto (horas desde registro):
    < 24h          → 100% del componente (ventana caliente)
    24h – 48h      →  67%
    48h – 72h      →  33%
    > 72h          →   0% (lead frío — sin fecha también recibe 0)

  Intención declarada (extraída por IA de conversación):
    alta           → 100% del componente
    media          →  50%
    baja / None    →   0%

Componentes del score (suma = 100):
  canal             →  15 pts máx
  cuota_inicial     →  20 pts máx
  pidio_cita        →  20 pts máx
  forma_pago        →  15 pts máx
  tiempo_contacto   →  15 pts máx
  intencion_ia      →  15 pts máx

Temperatura (umbrales dinámicos por percentil):
  Top 20%  → Caliente
  Sig. 50% → Tibio
  Bot. 30% → Frio
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ── Pesos por componente (pts máximos, deben sumar 100) ──────────────────────

PESO_CANAL         = 15
PESO_CUOTA_INICIAL = 20
PESO_PIDIO_CITA    = 20
PESO_FORMA_PAGO    = 15
PESO_TIEMPO        = 15
PESO_INTENCION_IA  = 15

assert (PESO_CANAL + PESO_CUOTA_INICIAL + PESO_PIDIO_CITA +
        PESO_FORMA_PAGO + PESO_TIEMPO + PESO_INTENCION_IA) == 100, \
    "Los pesos del scoring deben sumar 100"


# ── Tablas de puntuación calibradas con el histórico ─────────────────────────

_SCORE_CANAL = {
    "WhatsApp":       PESO_CANAL * 1.00,   # 9.5% → máximo del grupo
    "Formulario Web": PESO_CANAL * 0.95,   # 9.0%
    "Meta Ads":       PESO_CANAL * 0.85,   # 8.1%
}

_SCORE_CUOTA = {
    True:  PESO_CUOTA_INICIAL * 1.00,   # 10.9% → máximo
    False: PESO_CUOTA_INICIAL * 0.74,   # 8.1%
    None:  PESO_CUOTA_INICIAL * 0.64,   # 7.0%  → no informa
}

_SCORE_CITA = {
    True:  PESO_PIDIO_CITA * 1.00,   # 11.0% → máximo
    False: PESO_PIDIO_CITA * 0.74,   # 8.1%
    None:  PESO_PIDIO_CITA * 0.74,   # sin dato → tratamos como No
}

_SCORE_FORMA_PAGO = {
    "contado":    PESO_FORMA_PAGO * 1.00,   # 11.0% → máximo
    "leasing":    PESO_FORMA_PAGO * 0.82,   # ~9.0% estimado
    "no_informa": PESO_FORMA_PAGO * 0.73,   # 8.0%
    "credito":    PESO_FORMA_PAGO * 0.70,   # 7.7%
}

_SCORE_INTENCION = {
    "alta":  PESO_INTENCION_IA * 1.00,
    "media": PESO_INTENCION_IA * 0.50,
    "baja":  PESO_INTENCION_IA * 0.00,
    None:    PESO_INTENCION_IA * 0.00,
}

# Mapeo de nombres del DataFrame → nombres de columnas en Supabase
_COLUMNAS_SCORE_DB = {
    "lead_id":             "lead_id",
    "score_total":         "score_total",
    "temperatura":         "temperatura",
    "score_canal":         "score_canal",
    "score_tiempo":        "score_tiempo_respuesta",
    "score_cuota_inicial": "score_cuota_inicial",
    "score_forma_pago":    "score_forma_pago",
    "score_intencion_ia":  "score_intencion",
    "score_pidio_cita":    "score_pidio_cita",
    "explicacion":         "explicacion",
}

# ── Funciones de puntuación por componente ────────────────────────────────────

def _puntaje_canal(canal: Optional[str]) -> float:
    return _SCORE_CANAL.get(canal, PESO_CANAL * 0.85)


def _puntaje_cuota(
    presupuesto_cuota, forma_pago_ia: Optional[str]
) -> tuple[float, bool]:
    """
    Determina si el lead declaró cuota inicial.
    Retorna (puntaje, manifesto_cuota_bool).
    """
    manifesto = False

    if presupuesto_cuota is not None and presupuesto_cuota > 0:
        manifesto = True
    elif forma_pago_ia in ("credito", "leasing"):
        manifesto = True

    return _SCORE_CUOTA.get(manifesto, _SCORE_CUOTA[None]), manifesto


def _puntaje_cita(pidio_cita: Optional[bool]) -> float:
    return _SCORE_CITA.get(pidio_cita, _SCORE_CITA[None])


def _puntaje_forma_pago(forma_pago: Optional[str]) -> float:
    if forma_pago is None:
        return _SCORE_FORMA_PAGO["no_informa"]
    return _SCORE_FORMA_PAGO.get(forma_pago, _SCORE_FORMA_PAGO["no_informa"])


def _puntaje_tiempo(
    fecha_registro,
    ahora: datetime = None,
) -> tuple[float, Optional[float]]:
    """
    Calcula el puntaje según horas transcurridas desde el registro.
    Sin fecha válida → 0 pts (lead frío por tiempo, no neutro).
    Retorna (puntaje, horas_transcurridas).
    """
    if ahora is None:
        ahora = datetime.now(timezone.utc)

    # NaN de pandas es float — cubrir None, NaN y string vacío
    if (
        fecha_registro is None
        or isinstance(fecha_registro, float)
        or str(fecha_registro).strip() == ""
    ):
        return 0.0, None   # sin fecha = 0 pts, no neutro

    try:
        if isinstance(fecha_registro, str):
            dt = datetime.fromisoformat(fecha_registro)
        else:
            dt = fecha_registro

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        horas = (ahora - dt).total_seconds() / 3600

        if horas < 24:
            puntaje = PESO_TIEMPO * 1.00   # ventana caliente
        elif horas < 48:
            puntaje = PESO_TIEMPO * 0.67
        elif horas < 72:
            puntaje = PESO_TIEMPO * 0.33
        else:
            puntaje = PESO_TIEMPO * 0.00   # > 72h = 0 pts

        return puntaje, round(horas, 1)

    except (ValueError, TypeError) as e:
        logger.debug(f"No se pudo parsear fecha '{fecha_registro}': {e}")
        return 0.0, None


def _puntaje_intencion(intencion: Optional[str]) -> float:
    return _SCORE_INTENCION.get(intencion, _SCORE_INTENCION[None])


# ── Umbrales dinámicos por percentil ─────────────────────────────────────────

def _calibrar_umbrales(scores: list[float]) -> tuple[float, float]:
    """
    Calcula umbrales dinámicos basados en la distribución real del batch.
      Top 20%  → Caliente
      Sig. 50% → Tibio
      Bot. 30% → Frío

    Esto garantiza una distribución accionable independientemente de
    cuántos leads tengan datos de IA en el run actual.
    """
    serie = pd.Series(scores)
    umbral_caliente = round(serie.quantile(0.80), 2)
    umbral_tibio    = round(serie.quantile(0.30), 2)
    logger.info(
        f"Umbrales calibrados por percentil — "
        f"Caliente: ≥{umbral_caliente} (p80) | "
        f"Tibio: ≥{umbral_tibio} (p30) | "
        f"Frío: <{umbral_tibio}"
    )
    return umbral_caliente, umbral_tibio


def _temperatura(score: float, umbral_cal: float, umbral_tibio: float) -> str:
    if score >= umbral_cal:
        return "Caliente"
    elif score >= umbral_tibio:
        return "Tibio"
    return "Frio"


# ── Explicación legible ───────────────────────────────────────────────────────

def _generar_explicacion(
    canal: Optional[str],
    manifesto_cuota: bool,
    pidio_cita: Optional[bool],
    forma_pago: Optional[str],
    horas: Optional[float],
    intencion: Optional[str],
    temperatura: str,
) -> str:
    razones = []
    alertas = []   # ← separar razones positivas de alertas

    if intencion == "alta":
        razones.append("intención de compra alta declarada en conversación")
    elif intencion == "media":
        razones.append("intención media (evaluando opciones)")

    if pidio_cita:
        razones.append("pidió cita o cotización")

    if manifesto_cuota:
        razones.append("declaró cuota inicial o presupuesto")

    if forma_pago == "contado":
        razones.append("pago de contado")

    if canal == "WhatsApp":
        razones.append("canal WhatsApp (mayor tasa histórica de cierre)")

    # ── Tiempo: razón positiva vs alerta negativa ─────────────────────────
    if horas is not None:
        if horas < 24:
            razones.append(f"lead reciente ({horas:.0f}h)")
        elif 24 <= horas <= 72:
            alertas.append(f"lleva {horas:.0f}h sin contacto — gestionar hoy")
        else:  # horas > 72
            alertas.append(f"⚠ {horas:.0f}h sin contacto — riesgo de pérdida")

    if not razones and not alertas:
        razones.append("sin señales fuertes de intención")

    # ── Construir texto ───────────────────────────────────────────────────
    partes = []
    if razones:
        texto_razones = "; ".join(razones)
        partes.append(texto_razones[0].upper() + texto_razones[1:])
    if alertas:
        partes.append("; ".join(alertas))

    return f"[{temperatura}] " + ". ".join(partes) + "."


def persist_scores(df_scored: pd.DataFrame, run_id: str) -> None:
    from db.client import get_client
    db = get_client()

    # ── Fix: traer TODOS los lead_ids paginando ───────────────────────────
    leads_existentes = set()
    page_size = 1000
    offset = 0
    while True:
        resultado = (
            db.table("leads")
            .select("lead_id")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = resultado.data or []
        for row in batch:
            leads_existentes.add(row["lead_id"])
        if len(batch) < page_size:
            break
        offset += page_size

    logger.info(f"Leads existentes en BD: {len(leads_existentes)}")
    # ─────────────────────────────────────────────────────────────────────

    cols_presentes = [c for c in _COLUMNAS_SCORE_DB if c in df_scored.columns]
    df_db = df_scored[cols_presentes].rename(columns=_COLUMNAS_SCORE_DB).copy()
    df_db["pipeline_run_id"] = run_id

    logger.info(f"Scores antes de filtrar: {len(df_db)}")

    antes = len(df_db)
    df_db = df_db[df_db["lead_id"].isin(leads_existentes)]
    descartados = antes - len(df_db)

    logger.info(f"Scores después de filtrar: {len(df_db)}")

    if descartados > 0:
        logger.warning(
            f"{descartados} scores descartados por lead_id inexistente en BD"
        )

    records = [
        {k: (None if pd.isna(v) else v) for k, v in row.items()}
        for row in df_db.to_dict(orient="records")
    ]

    batch_size = 500
    for i in range(0, len(records), batch_size):
        db.table("lead_scores").upsert(
            records[i:i + batch_size],
            on_conflict="lead_id,pipeline_run_id"
        ).execute()

    logger.info(f"{len(records)} scores persistidos en Supabase")


# ── Función principal ─────────────────────────────────────────────────────────

def calcular_scores(
    df_leads: pd.DataFrame,
    extracciones: list[dict],
    ahora: datetime = None,
) -> pd.DataFrame:
    """
    Calcula el score de prioridad para cada lead activo (no duplicado).

    Flujo en tres pasos:
      1. Calcular componentes numéricos para todos los leads
      2. Calibrar umbrales de temperatura con la distribución real del batch
      3. Asignar temperatura y explicación con umbrales calibrados

    Args:
        df_leads:     DataFrame normalizado y deduplicado
        extracciones: lista de dicts con resultados de extract_ai
        ahora:        datetime de referencia (útil para tests)

    Returns:
        DataFrame con columnas de score añadidas, ordenado por score desc.
    """
    if ahora is None:
        ahora = datetime.now(timezone.utc)

    # Índice de extracciones por lead_id (solo exitosas)
    extraccion_por_lead: dict[str, dict] = {}
    for ext in extracciones:
        if ext.get("extraccion_exitosa") and ext.get("lead_id"):
            lead_id = str(ext["lead_id"])
            if lead_id not in extraccion_por_lead:
                extraccion_por_lead[lead_id] = ext

    # Solo leads activos (no duplicados)
    df = df_leads[~df_leads["es_duplicado"]].copy()

    logger.info(
        f"Calculando scores para {len(df):,} leads activos "
        f"({len(extraccion_por_lead)} con datos de IA)..."
    )

    # ── Paso 1: calcular componentes numéricos ────────────────────────────────
    scores_raw = []
    for _, row in df.iterrows():
        lead_id = str(row["lead_id"])
        ext     = extraccion_por_lead.get(lead_id, {})

        canal          = row.get("canal")
        fecha_registro = row.get("fecha_registro")

        presupuesto   = ext.get("presupuesto_cuota")
        forma_pago_ia = ext.get("forma_pago")
        intencion     = ext.get("intencion_declarada")
        pidio_cita_ia = ext.get("pidio_cita_cotizacion")

        forma_pago = forma_pago_ia or "no_informa"

        s_canal               = _puntaje_canal(canal)
        s_cuota, man_cuota    = _puntaje_cuota(presupuesto, forma_pago_ia)
        s_cita                = _puntaje_cita(pidio_cita_ia)
        s_forma_pago          = _puntaje_forma_pago(forma_pago)
        s_tiempo, horas       = _puntaje_tiempo(fecha_registro, ahora)
        s_intencion           = _puntaje_intencion(intencion)

        score_total = round(
            s_canal + s_cuota + s_cita + s_forma_pago + s_tiempo + s_intencion,
            2,
        )

        scores_raw.append({
            "lead_id":             lead_id,
            "score_total":         score_total,
            "score_canal":         round(s_canal, 2),
            "score_cuota_inicial": round(s_cuota, 2),
            "score_pidio_cita":    round(s_cita, 2),
            "score_forma_pago":    round(s_forma_pago, 2),
            "score_tiempo":        round(s_tiempo, 2),
            "score_intencion_ia":  round(s_intencion, 2),
            "horas_sin_contacto":  horas,
            "tiene_extraccion_ia": bool(ext),
            # temporales para paso 3
            "_canal":              canal,
            "_manifesto_cuota":    man_cuota,
            "_pidio_cita":         pidio_cita_ia,
            "_forma_pago":         forma_pago,
            "_horas":              horas,
            "_intencion":          intencion,
        })

    # ── Paso 2: calibrar umbrales con distribución real del batch ─────────────
    todos_scores = [r["score_total"] for r in scores_raw]
    umbral_cal, umbral_tibio = _calibrar_umbrales(todos_scores)

    # ── Paso 3: asignar temperatura y explicación ─────────────────────────────
    scores_final = []
    for r in scores_raw:
        temp = _temperatura(r["score_total"], umbral_cal, umbral_tibio)
        expl = _generar_explicacion(
            r["_canal"], r["_manifesto_cuota"], r["_pidio_cita"],
            r["_forma_pago"], r["_horas"], r["_intencion"], temp,
        )
        scores_final.append({
            "lead_id":             r["lead_id"],
            "score_total":         r["score_total"],
            "temperatura":         temp,
            "score_canal":         r["score_canal"],
            "score_cuota_inicial": r["score_cuota_inicial"],
            "score_pidio_cita":    r["score_pidio_cita"],
            "score_forma_pago":    r["score_forma_pago"],
            "score_tiempo":        r["score_tiempo"],
            "score_intencion_ia":  r["score_intencion_ia"],
            "horas_sin_contacto":  r["horas_sin_contacto"],
            "tiene_extraccion_ia": r["tiene_extraccion_ia"],
            "explicacion":         expl,
            "umbral_caliente":     umbral_cal,
            "umbral_tibio":        umbral_tibio,
        })

    df_scores = pd.DataFrame(scores_final)

    # Merge con DataFrame de leads
    df_resultado = df.merge(df_scores, on="lead_id", how="left")
    df_resultado = df_resultado.sort_values("score_total", ascending=False)

    # ── Resumen ───────────────────────────────────────────────────────────────
    calientes = (df_scores["temperatura"] == "Caliente").sum()
    tibios    = (df_scores["temperatura"] == "Tibio").sum()
    frios     = (df_scores["temperatura"] == "Frio").sum()

    logger.info("=== SCORING COMPLETO ===")
    logger.info(f"  Leads activos scoring  : {len(df_scores):,}")
    logger.info(f"  Calientes (≥{umbral_cal}) : {calientes:,}  (~20%)")
    logger.info(f"  Tibios    ({umbral_tibio}–{umbral_cal}) : {tibios:,}  (~50%)")
    logger.info(f"  Frios     (<{umbral_tibio})  : {frios:,}  (~30%)")
    logger.info(f"  Score promedio         : {df_scores['score_total'].mean():.1f}")
    logger.info(f"  Score máximo           : {df_scores['score_total'].max():.1f}")
    logger.info(f"  Score mínimo           : {df_scores['score_total'].min():.1f}")

    return df_resultado


def resumen_scoring(df: pd.DataFrame) -> None:
    """Imprime un resumen detallado del scoring para validación."""
    print("\n=== RESUMEN DE SCORING ===")

    print("\n--- Distribución de temperatura ---")
    print(df["temperatura"].value_counts())

    print("\n--- Score promedio por empresa ---")
    if "empresa_id" in df.columns:
        print(
            df.groupby("empresa_id")["score_total"]
            .agg(["mean", "min", "max"])
            .round(1)
        )

    print("\n--- Score promedio por canal ---")
    if "canal" in df.columns:
        print(
            df.groupby("canal")["score_total"]
            .agg(["mean", "count"])
            .round(1)
        )

    print("\n--- Top 10 leads (mayor score) ---")
    cols = [
        "lead_id", "nombre_cliente", "canal", "empresa_id",
        "score_total", "temperatura", "explicacion",
    ]
    cols_presentes = [c for c in cols if c in df.columns]
    print(df[cols_presentes].head(10).to_string())

    print("\n--- Distribución de score (percentiles) ---")
    print(df["score_total"].describe(percentiles=[.10, .25, .50, .75, .90]).round(1))

    print("\n--- Leads con extracción IA vs sin ella ---")
    if "tiene_extraccion_ia" in df.columns:
        resumen_ia = df.groupby("tiene_extraccion_ia")["score_total"].agg(
            ["count", "mean", "min", "max"]
        ).round(1)
        resumen_ia.index = ["Sin IA", "Con IA"]
        print(resumen_ia)


# ── Ejecución directa para prueba ─────────────────────────────────────────────

if __name__ == "__main__":
    import json
    from pathlib import Path

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s — %(levelname)s — %(message)s",
    )

    from pipeline.ingest import ingestar_todo
    from pipeline.normalize import normalizar_leads
    from pipeline.deduplicate import deduplicar

    # Cargar extracciones desde checkpoint
    checkpoint = Path("data/processed/extracciones.json")
    if checkpoint.exists():
        with open(checkpoint, "r", encoding="utf-8") as f:
            extracciones = json.load(f)
        print(f"Extracciones cargadas desde checkpoint: {len(extracciones)}")
    else:
        extracciones = []
        print("Sin checkpoint de extracciones — scores sin datos de IA")

    datos       = ingestar_todo()
    leads_norm  = normalizar_leads(datos["leads"], datos["catalogo"])
    leads_dedup = deduplicar(leads_norm)

    df_scored = calcular_scores(leads_dedup, extracciones)
    resumen_scoring(df_scored)

    print("\nScoring completo.")