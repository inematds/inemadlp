import asyncio
from pathlib import Path

import pytest

from inemadlp import worker
from inemadlp.config import load_settings
from inemadlp.downloader import DownloadError, DownloadResult
from inemadlp.store import ERROR, PENDING, READY, RUNNING, Store


@pytest.fixture
def ambiente(tmp_path):
    settings = load_settings({
        "DLP_PASSWORD": "s",
        "DLP_SECRET_KEY": "k",
        "DLP_UPLOAD_TOKEN": "t",
        "DLP_DATA_DIR": str(tmp_path),
    })
    return Store(settings.db_path), settings


def _download_falso(**kwargs):
    kwargs["on_title"]("Título Falso")
    kwargs["on_progress"](50.0)
    destino = Path(kwargs["destino"])
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / "v.mp4"
    arquivo.write_bytes(b"12345")
    return DownloadResult(path=arquivo, title="Título Falso", size=5)


def test_run_one_returns_false_when_queue_empty(ambiente):
    store, settings = ambiente
    assert worker.run_one(store, settings, now=1000, download_fn=_download_falso) is False


def test_run_one_completes_a_job(ambiente):
    store, settings = ambiente
    job = store.create("https://a", "video", now=1000)
    assert worker.run_one(store, settings, now=1001, download_fn=_download_falso) is True
    pronto = store.get(job.id)
    assert (pronto.status, pronto.filename, pronto.size) == (READY, "v.mp4", 5)
    assert pronto.title == "Título Falso"


def test_failed_download_becomes_error(ambiente):
    store, settings = ambiente
    job = store.create("https://a", "video", now=1000)

    def falha(**kwargs):
        raise DownloadError("ERROR: Unsupported URL")

    assert worker.run_one(store, settings, now=1001, download_fn=falha) is True
    falho = store.get(job.id)
    assert falho.status == ERROR
    assert "Unsupported URL" in falho.error


def test_unexpected_exception_becomes_error_not_crash(ambiente):
    store, settings = ambiente
    job = store.create("https://a", "video", now=1000)

    def explode(**kwargs):
        raise RuntimeError("disco cheio")

    assert worker.run_one(store, settings, now=1001, download_fn=explode) is True
    assert store.get(job.id).status == ERROR


def test_run_one_reaps_before_downloading(ambiente):
    store, settings = ambiente
    velho = store.create("https://velho", "video", now=0)
    store.claim_next(now=0)
    pasta = settings.downloads_dir / velho.id
    pasta.mkdir(parents=True)
    (pasta / "v.mp4").write_bytes(b"x")
    store.mark_ready(velho.id, "v.mp4", 1)

    store.create("https://novo", "video", now=7 * 3600)
    worker.run_one(store, settings, now=7 * 3600 + 1, download_fn=_download_falso)
    assert not pasta.exists()


def test_reap_failure_does_not_stop_processing(ambiente, monkeypatch):
    store, settings = ambiente
    store.create("https://a", "video", now=1000)

    def reap_quebrado(*args, **kwargs):
        raise OSError("disco com erro")

    monkeypatch.setattr(worker.reaper, "reap", reap_quebrado)
    assert worker.run_one(store, settings, now=1001, download_fn=_download_falso) is True


def test_claim_next_failure_returns_false(ambiente, monkeypatch):
    store, settings = ambiente
    store.create("https://a", "video", now=1000)

    def claim_quebrado(now):
        raise RuntimeError("sqlite lock")

    monkeypatch.setattr(store, "claim_next", claim_quebrado)
    assert worker.run_one(store, settings, now=1001, download_fn=_download_falso) is False


def test_mark_ready_failure_leaves_job_in_error(ambiente, monkeypatch):
    store, settings = ambiente
    job = store.create("https://a", "video", now=1000)

    def mark_ready_quebrado(job_id, filename, size):
        raise RuntimeError("disco cheio")

    monkeypatch.setattr(store, "mark_ready", mark_ready_quebrado)
    assert worker.run_one(store, settings, now=1001, download_fn=_download_falso) is True
    falho = store.get(job.id)
    assert falho.status == ERROR
    assert falho.status != RUNNING


def test_run_forever_survives_failing_iteration(ambiente):
    store, settings = ambiente
    store.create("https://a", "video", now=1000)

    chamadas = {"n": 0}
    original_run_one = worker.run_one

    def run_one_instavel(store, settings, now, download_fn=_download_falso):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise RuntimeError("falha inesperada na primeira iteração")
        return original_run_one(store, settings, now, download_fn=_download_falso)

    async def cenario():
        import inemadlp.worker as worker_mod
        antigo = worker_mod.run_one
        worker_mod.run_one = run_one_instavel
        try:
            tarefa = asyncio.create_task(
                worker_mod.run_forever(store, settings, sleep_seconds=0.01)
            )
            for _ in range(200):
                if chamadas["n"] >= 2:
                    break
                await asyncio.sleep(0.01)
            tarefa.cancel()
            with pytest.raises(asyncio.CancelledError):
                await tarefa
        finally:
            worker_mod.run_one = antigo

    asyncio.run(cenario())
    assert chamadas["n"] >= 2


def test_recover_on_boot_clears_orphans(ambiente):
    store, _ = ambiente
    job = store.create("https://a", "video", now=1000)
    store.claim_next(now=1001)
    assert worker.recover_on_boot(store) == 1
    recuperado = store.get(job.id)
    assert recuperado.status == ERROR
    assert "reiniciado" in recuperado.error
    assert store.create("https://b", "video", now=2000).status == PENDING
