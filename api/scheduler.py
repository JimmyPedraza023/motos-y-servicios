import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio

logger = logging.getLogger("api.scheduler")

# Singleton del scheduler — se inicia en lifespan de main.py
scheduler = AsyncIOScheduler(timezone="America/Bogota")


async def _job_pipeline_nocturno():
    """
    Job nocturno: ejecuta el pipeline completo.
    Corre a las 02:00 hora Colombia todos los días.
    """
    logger.info("Cron nocturno — iniciando pipeline automático")
    try:
        from run_pipeline import run
        import asyncio
        # run() es síncrono — lo corremos en el executor para no bloquear el event loop
        loop = asyncio.get_event_loop()
        resultado = await loop.run_in_executor(None, lambda: run(trigger_tipo="cron"))
        logger.info(f"Cron completado — {resultado}")
    except Exception as e:
        logger.error(f"Cron fallido: {e}")


def iniciar_scheduler():
    scheduler.add_job(
        _job_pipeline_nocturno,
        trigger=CronTrigger(hour=2, minute=0),   # 02:00 hora Colombia
        id="pipeline_nocturno",
        name="Pipeline nocturno de priorización",
        replace_existing=True,
        misfire_grace_time=3600,  # si el server estuvo caído, ejecuta hasta 1h tarde
    )
    scheduler.start()
    logger.info("✔ Scheduler iniciado — pipeline nocturno programado a las 02:00 COT")


def detener_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler detenido")