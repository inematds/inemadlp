import pytest

from inemadlp import reaper
from inemadlp.store import EXPIRED, READY, Store

HORA = 3600


@pytest.fixture
def ambiente(tmp_path):
    store = Store(tmp_path / "test.db")
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    return store, downloads


def _job_pronto(store, downloads, url, criado_em):
    job = store.create(url, "video", now=criado_em)
    store.claim_next(now=criado_em)
    pasta = downloads / job.id
    pasta.mkdir()
    (pasta / "v.mp4").write_bytes(b"conteudo")
    store.mark_ready(job.id, "v.mp4", 8)
    return job


def test_deletes_files_past_ttl(ambiente):
    store, downloads = ambiente
    job = _job_pronto(store, downloads, "https://a", criado_em=0)
    assert reaper.reap(store, downloads, ttl_hours=6, now=7 * HORA) == 1
    assert not (downloads / job.id).exists()
    assert store.get(job.id).status == EXPIRED
    assert store.get(job.id).filename is None


def test_keeps_files_inside_ttl(ambiente):
    store, downloads = ambiente
    job = _job_pronto(store, downloads, "https://a", criado_em=0)
    assert reaper.reap(store, downloads, ttl_hours=6, now=5 * HORA) == 0
    assert (downloads / job.id).exists()
    assert store.get(job.id).status == READY


def test_is_idempotent(ambiente):
    store, downloads = ambiente
    _job_pronto(store, downloads, "https://a", criado_em=0)
    reaper.reap(store, downloads, ttl_hours=6, now=7 * HORA)
    assert reaper.reap(store, downloads, ttl_hours=6, now=8 * HORA) == 0


def test_survives_missing_folder(ambiente):
    store, downloads = ambiente
    job = _job_pronto(store, downloads, "https://a", criado_em=0)
    (downloads / job.id / "v.mp4").unlink()
    (downloads / job.id).rmdir()
    assert reaper.reap(store, downloads, ttl_hours=6, now=7 * HORA) == 1
    assert store.get(job.id).status == EXPIRED


def test_purges_history_after_thirty_days(ambiente):
    store, downloads = ambiente
    job = _job_pronto(store, downloads, "https://a", criado_em=0)
    reaper.reap(store, downloads, ttl_hours=6, now=7 * HORA)
    reaper.reap(store, downloads, ttl_hours=6, now=31 * 24 * HORA)
    assert store.get(job.id) is None
