"""
Módulo de extracción con IA: usa DeepSeek V4 Flash (NVIDIA NIM) para extraer
información estructurada de las conversaciones de WhatsApp.

Por cada conversación extrae 6 campos:
  1. modelo_interes        — modelo de moto mencionado por el CLIENTE
  2. presupuesto_cuota     — valor monetario declarado por el CLIENTE como
                             presupuesto o cuota inicial (no precio de catálogo)
  3. forma_pago            — contado | credito | leasing | no_informa
  4. intencion_declarada   — alta | media | baja
  5. objecion_principal    — objeción o freno principal expresado por el CLIENTE
  6. pidio_cita_cotizacion — true si el CLIENTE solicitó cita o cotización

Mejoras implementadas:
  - Validación de respuesta con Pydantic (tipos + valores permitidos)
  - Errores retornan None en campos afectados, no valores por defecto falsos
  - Prompt mejorado: distinción cliente/asesor, presupuesto vs precio catálogo
  - Modelo y URL configurables desde .env
  - Métricas de tiempo total al finalizar
  - Checkpoint por grupo para reanudar runs interrumpidos
  - Backoff progresivo ante errores 429/504/529
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import openai
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, field_validator, ValidationError

from db.client import get_client

load_dotenv()

logger = logging.getLogger(__name__)


# ── Configuración desde .env ──────────────────────────────────────────────────

MODELO_IA     = os.getenv("AI_MODEL",      "deepseek-ai/deepseek-v4-flash-0731")
NVIDIA_BASE_URL = os.getenv("AI_BASE_URL", "https://integrate.api.nvidia.com/v1")
MAX_TOKENS    = int(os.getenv("AI_MAX_TOKENS", "512"))
TAMANO_GRUPO  = 10    # conversaciones por grupo con checkpoint
PAUSA_GRUPO   = 1.0   # segundos entre grupos
MAX_REINTENTOS = 3

CHECKPOINT_PATH = "data/processed/extracciones.json"


# ── Modelo Pydantic para validar la respuesta de la IA ───────────────────────

class ExtraccionIA(BaseModel):
    modelo_interes: Optional[str] = None
    presupuesto_cuota: Optional[float] = None
    forma_pago: str
    intencion_declarada: str
    objecion_principal: Optional[str] = None
    pidio_cita_cotizacion: bool

    @field_validator("forma_pago")
    @classmethod
    def validar_forma_pago(cls, v: str) -> str:
        permitidos = {"contado", "credito", "leasing", "no_informa"}
        if v not in permitidos:
            raise ValueError(f"forma_pago invalida: '{v}'. Debe ser una de {permitidos}")
        return v

    @field_validator("intencion_declarada")
    @classmethod
    def validar_intencion(cls, v: str) -> str:
        permitidos = {"alta", "media", "baja"}
        if v not in permitidos:
            raise ValueError(f"intencion_declarada invalida: '{v}'. Debe ser una de {permitidos}")
        return v

    @field_validator("presupuesto_cuota", mode="before")
    @classmethod
    def validar_presupuesto(cls, v) -> Optional[float]:
        if v is None:
            return None
        try:
            valor = float(str(v).replace(",", "").replace(".", ""))
            # Filtrar valores irreales para el mercado colombiano de motos
            if valor < 50_000 or valor > 50_000_000:
                return None
            return valor
        except (ValueError, TypeError):
            return None


# ── Prompt del sistema ────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres un asistente de análisis comercial para una empresa colombiana
que vende motos. Tu tarea es extraer información estructurada de conversaciones de
WhatsApp entre CLIENTES y ASESORES de ventas.

REGLAS IMPORTANTES:
- Responde ÚNICAMENTE con un objeto JSON válido, sin texto adicional, sin backticks,
  sin explicaciones previas ni posteriores.
- Si un campo no se puede determinar con certeza desde la conversación, usa null.
- Distingue siempre entre lo que dice el CLIENTE y lo que dice el ASESOR.

REGLAS POR CAMPO:

modelo_interes:
  - El modelo de moto que el CLIENTE menciona querer o preguntar.
  - Si el asesor menciona modelos que el cliente no confirma, usa null.

presupuesto_cuota:
  - Extrae SOLO un valor monetario que el CLIENTE declare explícitamente
    como su presupuesto, cuota inicial o cuota mensual que puede pagar.
  - NO extraigas precios de catálogo que el ASESOR mencione.
  - NO extraigas valores que el cliente rechace o diga que no puede pagar.
  - Extrae solo el número entero (sin signos de pesos, sin puntos de miles).
  - Si no hay un valor declarado por el cliente, usa null.

forma_pago:
  - Usa exactamente uno de: contado, credito, leasing, no_informa.
  - Basado en lo que el CLIENTE declara, no en lo que el asesor ofrece.

intencion_declarada:
  - alta: el cliente quiere comprar pronto, pregunta por disponibilidad,
          pide cita, tiene presupuesto claro, está decidido.
  - media: el cliente está evaluando, compara opciones, pide información
           detallada pero no confirma intención de compra.
  - baja: el cliente solo pregunta precios de manera general, tiene muchas
          dudas, menciona que "está mirando", no muestra urgencia.

objecion_principal:
  - El freno o duda más importante que expresa el CLIENTE.
  - En máximo 10 palabras, en español.
  - Si no hay objeción clara, usa null.

pidio_cita_cotizacion:
  - true SOLO si el CLIENTE pidió explícitamente una cita, una visita
    al punto de venta, o una cotización formal.
  - false si fue el asesor quien propuso la cita sin que el cliente la pidiera.

FORMATO DE RESPUESTA (sin variaciones, sin texto adicional):
{
  "modelo_interes": "string o null",
  "presupuesto_cuota": número entero o null,
  "forma_pago": "contado|credito|leasing|no_informa",
  "intencion_declarada": "alta|media|baja",
  "objecion_principal": "string o null",
  "pidio_cita_cotizacion": true o false
}"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _formatear_conversacion(conversacion: dict) -> str:
    """Convierte el objeto de conversación en texto plano para el prompt."""
    mensajes = conversacion.get("mensajes", [])
    lineas = []
    for msg in mensajes:
        emisor = msg.get("emisor", "desconocido").upper()
        hora   = msg.get("hora", "")
        texto  = msg.get("texto", "").strip()
        if texto:
            lineas.append(f"[{hora}] {emisor}: {texto}")
    return "\n".join(lineas)


def _limpiar_json(contenido: str) -> str:
    """
    Elimina backticks y prefijo 'json' por si el modelo envuelve
    la respuesta en un bloque de código markdown.
    """
    contenido = contenido.strip()
    if contenido.startswith("```"):
        partes   = contenido.split("```")
        contenido = partes[1].strip()
        if contenido.startswith("json"):
            contenido = contenido[4:].strip()
    return contenido


def _resultado_error(conv_id: str, error: str, lead_id: str = None) -> dict:
    """
    Retorna un resultado con campos None para conversaciones fallidas.
    NO asigna valores por defecto que contaminen el scoring.
    La bandera extraccion_exitosa=False permite filtrarlos en score.py.
    """
    return {
        "conversacion_id":    conv_id,
        "lead_id":            lead_id,
        "modelo_interes":     None,
        "presupuesto_cuota":  None,
        "forma_pago":         None,   # None, no "no_informa"
        "intencion_declarada": None,  # None, no "baja"
        "objecion_principal": None,
        "pidio_cita_cotizacion": None,  # None, no False
        "extraccion_exitosa": False,
        "modelo_ia_usado":    MODELO_IA,
        "tokens_usados":      0,
        "raw_response":       None,
        "error":              error,
    }


def guardar_resultados(
    resultados: list[dict],
    path: str = CHECKPOINT_PATH,
) -> None:
    """Persiste los resultados a disco como respaldo ante interrupciones."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"Checkpoint guardado: {len(resultados)} registros → {path}")


def cargar_resultados_previos(path: str = CHECKPOINT_PATH) -> list[dict]:
    """Carga resultados previos para reanudar un run interrumpido."""
    if not Path(path).exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        datos = json.load(f)
    logger.info(f"Checkpoint cargado: {len(datos)} registros desde {path}")
    return datos


# ── Extracción de una conversación ────────────────────────────────────────────

def _extraer_una(cliente: OpenAI, conversacion: dict) -> dict:
    """
    Llama al modelo para extraer los 6 campos de una conversación.
    Valida la respuesta con Pydantic antes de retornarla.
    En caso de error retorna campos None (no valores por defecto falsos).
    """
    conv_id = conversacion.get("conversacion_id", "?")
    lead_id = conversacion.get("lead_id")
    texto_conv = _formatear_conversacion(conversacion)

    if not texto_conv.strip():
        logger.warning(f"[{conv_id}] Conversación vacía, saltando.")
        return _resultado_error(conv_id, "conversacion_vacia", lead_id=lead_id)

    user_prompt = (
        "Analiza esta conversación de WhatsApp y extrae la información solicitada:\n\n"
        + texto_conv
    )

    for intento in range(1, MAX_REINTENTOS + 1):
        try:
            response = cliente.chat.completions.create(
                model=MODELO_IA,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0.1,
                top_p=0.95,
                max_tokens=MAX_TOKENS,
                stream=False,
                extra_body={"thinking": False},
            )

            contenido_raw = response.choices[0].message.content

            if contenido_raw is None:
                raise ValueError("El modelo retornó content=None")

            contenido  = _limpiar_json(contenido_raw)
            datos_raw  = json.loads(contenido)

            # Validación con Pydantic — tipos y valores permitidos
            extraccion = ExtraccionIA(**datos_raw)

            tokens_usados = response.usage.total_tokens if response.usage else 0

            return {
                "conversacion_id":       conv_id,
                "lead_id":               lead_id,
                "modelo_interes":        extraccion.modelo_interes,
                "presupuesto_cuota":     extraccion.presupuesto_cuota,
                "forma_pago":            extraccion.forma_pago,
                "intencion_declarada":   extraccion.intencion_declarada,
                "objecion_principal":    extraccion.objecion_principal,
                "pidio_cita_cotizacion": extraccion.pidio_cita_cotizacion,
                "extraccion_exitosa":    True,
                "modelo_ia_usado":       MODELO_IA,
                "tokens_usados":         tokens_usados,
                "raw_response":          contenido,
                "error":                 None,
            }

        except json.JSONDecodeError as e:
            logger.warning(
                f"[{conv_id}] Intento {intento}/{MAX_REINTENTOS}: JSON invalido — {e}"
            )
        except ValidationError as e:
            logger.warning(
                f"[{conv_id}] Intento {intento}/{MAX_REINTENTOS}: "
                f"Validacion Pydantic fallida — {e.error_count()} error(es)"
            )
        except openai.RateLimitError:
            espera = 10 * intento
            logger.warning(f"[{conv_id}] Rate limit (429), esperando {espera}s...")
            time.sleep(espera)
            continue  # no cuenta como intento fallido
        except openai.APIStatusError as e:
            if e.status_code in (504, 529):
                espera = 2 ** intento
                logger.warning(
                    f"[{conv_id}] HTTP {e.status_code}, esperando {espera}s..."
                )
                time.sleep(espera)
                continue
            logger.error(
                f"[{conv_id}] Error API {e.status_code} "
                f"intento {intento}/{MAX_REINTENTOS}: {e.message}"
            )
        except ValueError as e:
            logger.warning(
                f"[{conv_id}] Intento {intento}/{MAX_REINTENTOS}: {e}"
            )
        except Exception as e:
            logger.error(
                f"[{conv_id}] Error inesperado "
                f"intento {intento}/{MAX_REINTENTOS}: {e}"
            )

        if intento < MAX_REINTENTOS:
            time.sleep(2 ** intento)  # backoff: 2s, 4s

    return _resultado_error(conv_id, "max_reintentos_agotados", lead_id=lead_id)


# ── Función principal ─────────────────────────────────────────────────────────

def extraer_conversaciones(
    conversaciones: list[dict],
    limite: int = None,
    reanudar: bool = True,
    run_id: str = None, 
) -> list[dict]:
    """
    Procesa todas las conversaciones y retorna una lista de dicts
    con los campos extraídos por IA.

    Args:
        conversaciones: lista de objetos conversación del JSON fuente
        limite:         si se pasa, procesa solo los primeros N (modo prueba)
        reanudar:       si True, carga checkpoint previo y salta ya procesadas
    """
    api_key = os.getenv("AI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "AI_API_KEY no está definida en el entorno. "
            "Agrégala al archivo .env antes de ejecutar."
        )

    cliente = OpenAI(base_url=NVIDIA_BASE_URL, api_key=api_key)

    if limite:
        conversaciones = conversaciones[:limite]
        logger.info(f"Modo prueba: procesando solo {limite} conversaciones.")

    # Reanudación desde checkpoint
    resultados: list[dict] = []
    ids_procesados: set[str] = set()

    if reanudar:
        resultados = cargar_resultados_previos()
        ids_procesados = {r["conversacion_id"] for r in resultados}
        if ids_procesados:
            logger.info(
                f"Reanudando: {len(ids_procesados)} ya procesadas, saltando..."
            )

    pendientes = [
        c for c in conversaciones
        if c.get("conversacion_id") not in ids_procesados
    ]

    total = len(pendientes)
    if total == 0:
        logger.info("Todas las conversaciones ya fueron procesadas.")
        if run_id:
            # Traer los conversacion_id que realmente existen en Supabase
            db = get_client()
            ids_en_bd = {
                r["conversacion_id"]
                for r in db.table("conversaciones").select("conversacion_id").execute().data
            }

            exitosas_checkpoint = [
                r for r in resultados
                if r.get("extraccion_exitosa")
                and r.get("lead_id")
                and r.get("conversacion_id") in ids_en_bd
            ]

            logger.info(f"Persistiendo {len(exitosas_checkpoint)} extracciones desde checkpoint...")
            for r in exitosas_checkpoint:
                persist_extraccion(r, run_id)
            logger.info("Persistencia desde checkpoint completa.")
        return resultados

    tokens_totales = sum(r.get("tokens_usados", 0) for r in resultados)
    tiempo_inicio  = time.time()

    logger.info(
        f"Iniciando extracción IA sobre {total} conversaciones pendientes "
        f"con modelo {MODELO_IA}..."
    )

    for i in range(0, total, TAMANO_GRUPO):
        grupo       = pendientes[i: i + TAMANO_GRUPO]
        num_grupo   = i // TAMANO_GRUPO + 1
        total_grupos = (total + TAMANO_GRUPO - 1) // TAMANO_GRUPO

        logger.info(
            f"Grupo {num_grupo}/{total_grupos} "
            f"({i + 1}–{min(i + TAMANO_GRUPO, total)} de {total})..."
        )

        for conv in grupo:
            resultado = _extraer_una(cliente, conv)
            resultados.append(resultado)
            tokens_totales += resultado.get("tokens_usados", 0)

            if resultado.get("extraccion_exitosa") and run_id:
                persist_extraccion(resultado, run_id)

        # Checkpoint después de cada grupo
        guardar_resultados(resultados)

        if i + TAMANO_GRUPO < total:
            time.sleep(PAUSA_GRUPO)

    # ── Métricas finales ──────────────────────────────────────────────────────
    tiempo_total = time.time() - tiempo_inicio
    minutos  = int(tiempo_total // 60)
    segundos = int(tiempo_total % 60)
    exitosas = sum(1 for r in resultados if r.get("extraccion_exitosa"))
    fallidas = len(resultados) - exitosas

    logger.info("=" * 50)
    logger.info("EXTRACCIÓN IA COMPLETA — MÉTRICAS")
    logger.info("=" * 50)
    logger.info(f"  Conversaciones procesadas : {len(resultados)}")
    logger.info(f"  Exitosas                  : {exitosas}")
    logger.info(f"  Fallidas                  : {fallidas}")
    logger.info(f"  Tokens totales usados     : {tokens_totales:,}")
    logger.info(f"  Tiempo total              : {minutos}m {segundos}s")
    logger.info("=" * 50)

    return resultados


def load_conversaciones():
    db = get_client()
    # Solo las que no tienen extracción aún (evita re-procesar en re-ejecuciones)
    result = db.table("conversaciones").select(
        "conversacion_id, lead_id, raw_json"
    ).execute()
    return result.data


def persist_extraccion(resultado: dict, run_id: str = None) -> None:
    from db.client import get_client
    import json
    db = get_client()

    raw = resultado.get("raw_response")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {"raw": raw}

    record = {
        "conversacion_id":       resultado.get("conversacion_id"),
        "lead_id":               resultado.get("lead_id"),
        "modelo_interes":        resultado.get("modelo_interes"),
        "presupuesto_cuota":     resultado.get("presupuesto_cuota"),
        "forma_pago":            resultado.get("forma_pago"),
        "intencion_declarada":   resultado.get("intencion_declarada"),
        "objecion_principal":    resultado.get("objecion_principal"),
        "pidio_cita_cotizacion": resultado.get("pidio_cita_cotizacion"),
        "modelo_ia_usado":       resultado.get("modelo_ia_usado"),
        "tokens_usados":         resultado.get("tokens_usados"),
        "raw_response":          raw,  # ← ya como dict
    }

    record = {k: v for k, v in record.items() if v is not None}

    db.table("conversacion_extracciones").upsert(
        record, on_conflict="conversacion_id"
    ).execute()


# ── Ejecución directa ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s — %(levelname)s — %(message)s",
    )
    from pipeline.ingest import ingestar_todo

    datos = ingestar_todo()

    # Para prueba:       limite=5
    # Para run completo: sin límite
    resultados = extraer_conversaciones(datos["conversaciones"])

    exitosas = sum(1 for r in resultados if r.get("extraccion_exitosa"))
    print(f"\nRun completo — {exitosas}/{len(resultados)} extracciones exitosas.")