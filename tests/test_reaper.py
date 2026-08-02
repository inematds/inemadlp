import pytest

from inemadlp import reaper
from inemadlp.store import ERROR, EXPIRED, PENDING, READY, RUNNING, Store

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


def test_permission_error_not_counted_and_retried(ambiente, monkeypatch):
    """Pasta que não pode ser removida não é contada e fica READY para retry."""
    store, downloads = ambiente
    job = _job_pronto(store, downloads, "https://a", criado_em=0)

    # Monkeypatch shutil.rmtree para simular erro de permissão
    import shutil
    original_rmtree = shutil.rmtree
    def mock_rmtree(path, *args, **kwargs):
        raise PermissionError("Permission denied")
    monkeypatch.setattr("shutil.rmtree", mock_rmtree)

    # Tenta remover - deve falhar silenciosamente (apenas log)
    assert reaper.reap(store, downloads, ttl_hours=6, now=7 * HORA) == 0

    # Arquivo ainda deve existir no disco
    assert (downloads / job.id / "v.mp4").exists()

    # Job deve continuar READY (não marcado como expirado)
    assert store.get(job.id).status == READY

    # Restaura para o próximo teste
    monkeypatch.setattr("shutil.rmtree", original_rmtree)


def test_deletes_dir_of_error_job_past_ttl(ambiente):
    """FINDING 1: job que terminou em erro (ex.: container reiniciado a meio do
    download) também deve ter sua pasta reclamada passado o TTL — hoje
    list_expirable só olha READY, então isso falha sem o fix."""
    store, downloads = ambiente
    job = store.create("https://a", "video", now=0)
    store.claim_next(now=0)
    pasta = downloads / job.id
    pasta.mkdir()
    (pasta / "v.mp4.part").write_bytes(b"fragmento")
    store.mark_error(job.id, "container reiniciado")

    assert reaper.reap(store, downloads, ttl_hours=6, now=7 * HORA) == 1
    assert not pasta.exists()
    assert store.get(job.id).status == EXPIRED


def test_sweeps_orphan_directory_with_no_db_row(ambiente):
    """FINDING 1: pasta cujo job já foi purgado do banco (error > 30 dias) fica
    órfã e deve ser varrida mesmo sem nenhuma linha apontando pra ela."""
    store, downloads = ambiente
    orfa = downloads / "sem-dono-nenhum"
    orfa.mkdir()
    (orfa / "lixo.part").write_bytes(b"x")

    assert reaper.reap(store, downloads, ttl_hours=6, now=7 * HORA) == 1
    assert not orfa.exists()


def test_orphan_sweep_never_touches_pending_or_running_job_dir(ambiente):
    """A varredura de órfãos não pode apagar a pasta de um job pending/running
    (a pasta existe mas o job ainda não terminou)."""
    store, downloads = ambiente
    rodando = store.create("https://b", "video", now=0)
    store.claim_next(now=0)

    pendente = store.create("https://a", "video", now=0)
    pasta_pendente = downloads / pendente.id
    pasta_pendente.mkdir()
    (pasta_pendente / "v.mp4.part").write_bytes(b"em andamento")
    pasta_rodando = downloads / rodando.id
    pasta_rodando.mkdir()
    (pasta_rodando / "v.mp4.part").write_bytes(b"baixando")

    assert reaper.reap(store, downloads, ttl_hours=6, now=7 * HORA) == 0
    assert pasta_pendente.exists()
    assert pasta_rodando.exists()
    assert store.get(pendente.id).status == PENDING
    assert store.get(rodando.id).status == RUNNING


def test_missing_folder_counted_and_marked_expired(ambiente):
    """Pasta que já foi removida é contada e marcada como expirada."""
    store, downloads = ambiente
    job = _job_pronto(store, downloads, "https://a", criado_em=0)

    # Remove a pasta antes do reap
    (downloads / job.id / "v.mp4").unlink()
    (downloads / job.id).rmdir()

    # Deve contar como deletada mesmo que a pasta não exista
    assert reaper.reap(store, downloads, ttl_hours=6, now=7 * HORA) == 1

    # Job deve estar marcado como expirado
    assert store.get(job.id).status == EXPIRED
    assert store.get(job.id).filename is None
