"""Laço que consome a fila. Um job por vez."""

import asyncio
import logging
import time

from inemadlp import downloader, reaper
from inemadlp.config import Settings
from inemadlp.store import Store

logger = logging.getLogger(__name__)

BOOT_MESSAGE = "o serviço foi reiniciado durante o download"


def recover_on_boot(store: Store) -> int:
    return store.reset_running_to_error(BOOT_MESSAGE)


def run_one(store: Store, settings: Settings, now: int, download_fn=downloader.download) -> bool:
    # Libera espaço antes de baixar: disco cheio é um modo de falha real.
    reaper.reap(store, settings.downloads_dir, settings.ttl_hours, now)

    job = store.claim_next(now=now)
    if job is None:
        return False

    try:
        resultado = download_fn(
            url=job.url,
            fmt=job.format,
            destino=settings.downloads_dir / job.id,
            cookies_path=settings.cookies_path,
            on_progress=lambda pct: store.set_progress(job.id, pct),
            on_title=lambda titulo: store.set_title(job.id, titulo),
        )
    except Exception as erro:  # inclusive DownloadError: nada derruba o worker
        logger.warning("job %s falhou: %s", job.id, erro)
        store.mark_error(job.id, str(erro))
        return True

    store.mark_ready(job.id, resultado.path.name, resultado.size)
    return True


async def run_forever(store: Store, settings: Settings, sleep_seconds: float = 2.0) -> None:
    while True:
        processou = await asyncio.to_thread(run_one, store, settings, int(time.time()))
        if not processou:
            await asyncio.sleep(sleep_seconds)
