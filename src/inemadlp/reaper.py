"""Apaga o que passou do TTL. Recebe o relógio por parâmetro para ser testável."""

import shutil
from pathlib import Path

from inemadlp.store import Store

HISTORY_DAYS = 30


def reap(store: Store, downloads_dir: Path, ttl_hours: int, now: int) -> int:
    corte = now - ttl_hours * 3600
    apagados = 0
    for job in store.list_expirable(cutoff=corte):
        shutil.rmtree(Path(downloads_dir) / job.id, ignore_errors=True)
        store.mark_expired(job.id)
        apagados += 1
    store.delete_older_than(cutoff=now - HISTORY_DAYS * 86400)
    return apagados
