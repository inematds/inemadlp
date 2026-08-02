"""Apaga o que passou do TTL. Recebe o relógio por parâmetro para ser testável.

Retorna a contagem de pastas realmente removidas do disco.
"""

import logging
import shutil
from pathlib import Path

from inemadlp.store import Store

logger = logging.getLogger(__name__)

HISTORY_DAYS = 30


def reap(store: Store, downloads_dir: Path, ttl_hours: int, now: int) -> int:
    """Remove pastas de jobs expirados, marca como EXPIRED, purga histórico.

    Retorna a contagem de pastas efetivamente removidas do disco.
    Se uma pasta não pode ser removida (erro de permissão, I/O, etc.),
    registra em log, não a conta, e não marca como expirada para retry posterior.
    """
    corte = now - ttl_hours * 3600
    apagados = 0
    for job in store.list_expirable(cutoff=corte):
        pasta = Path(downloads_dir) / job.id
        try:
            shutil.rmtree(pasta)
            store.mark_expired(job.id)
            apagados += 1
        except FileNotFoundError:
            # Pasta já foi removida - trata como sucesso
            store.mark_expired(job.id)
            apagados += 1
        except (PermissionError, OSError) as e:
            # Erro de permissão ou I/O - registra e não marca como expirado
            # Próxima rodada fará retry
            logger.error(f"Não foi possível remover pasta de job {job.id}: {e}")

    apagados += _varrer_orfaos(store, downloads_dir)

    store.delete_older_than(cutoff=now - HISTORY_DAYS * 86400)
    return apagados


def _varrer_orfaos(store: Store, downloads_dir: Path) -> int:
    """Remove pastas em downloads_dir sem linha correspondente no banco.

    Cobre o caso de jobs 'error' cuja linha já foi purgada por delete_older_than
    (fica órfão pois o reaper baseado em job não o encontra mais). Nunca toca
    em uma pasta cujo job ainda está pending/running (linha ainda existe -> não é
    órfã) nem em qualquer pasta que ainda tenha linha no banco.
    """
    downloads_dir = Path(downloads_dir)
    if not downloads_dir.is_dir():
        return 0

    conhecidos = store.known_ids()
    apagados = 0
    for pasta in downloads_dir.iterdir():
        if not pasta.is_dir() or pasta.name in conhecidos:
            continue
        try:
            shutil.rmtree(pasta)
            apagados += 1
        except (PermissionError, OSError) as e:
            logger.error(f"Não foi possível remover pasta órfã {pasta}: {e}")
    return apagados
