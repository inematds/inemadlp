import pytest

from inemadlp.store import ERROR, EXPIRED, PENDING, READY, RUNNING, Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "test.db")


def test_create_starts_pending(store):
    job = store.create("https://exemplo/v", "video", now=1000)
    assert job.status == PENDING
    assert job.progress == 0
    assert job.url == "https://exemplo/v"
    assert job.format == "video"
    assert store.get(job.id).id == job.id


def test_list_all_newest_first(store):
    antigo = store.create("https://a", "video", now=1000)
    novo = store.create("https://b", "audio", now=2000)
    assert [j.id for j in store.list_all()] == [novo.id, antigo.id]


def test_claim_next_takes_oldest_pending_once(store):
    primeiro = store.create("https://a", "video", now=1000)
    store.create("https://b", "video", now=2000)
    reivindicado = store.claim_next(now=3000)
    assert reivindicado.id == primeiro.id
    assert reivindicado.status == RUNNING
    assert store.claim_next(now=3001).url == "https://b"
    assert store.claim_next(now=3002) is None


def test_progress_and_ready(store):
    job = store.create("https://a", "video", now=1000)
    store.claim_next(now=1001)
    store.set_progress(job.id, 42.5)
    store.set_title(job.id, "Um Vídeo")
    assert store.get(job.id).progress == 42.5
    store.mark_ready(job.id, "video.mp4", 1234)
    pronto = store.get(job.id)
    assert (pronto.status, pronto.filename, pronto.size, pronto.title) == (
        READY, "video.mp4", 1234, "Um Vídeo",
    )


def test_mark_error_records_message(store):
    job = store.create("https://a", "video", now=1000)
    store.mark_error(job.id, "Sign in to confirm")
    falho = store.get(job.id)
    assert falho.status == ERROR
    assert falho.error == "Sign in to confirm"


def test_reset_running_to_error(store):
    job = store.create("https://a", "video", now=1000)
    store.claim_next(now=1001)
    assert store.reset_running_to_error("container reiniciado") == 1
    assert store.get(job.id).status == ERROR
    assert store.reset_running_to_error("de novo") == 0


def test_list_expirable_only_ready_past_cutoff(store):
    velho = store.create("https://a", "video", now=1000)
    store.claim_next(now=1001)
    store.mark_ready(velho.id, "a.mp4", 10)
    recente = store.create("https://b", "video", now=9000)
    store.claim_next(now=9001)
    store.mark_ready(recente.id, "b.mp4", 10)
    assert [j.id for j in store.list_expirable(cutoff=5000)] == [velho.id]


def test_list_expirable_includes_error_jobs_past_cutoff(store):
    falho = store.create("https://a", "video", now=1000)
    store.claim_next(now=1001)
    store.mark_error(falho.id, "container reiniciado")
    assert [j.id for j in store.list_expirable(cutoff=5000)] == [falho.id]


def test_list_expirable_excludes_pending_and_running(store):
    store.create("https://a", "video", now=1000)  # fica pending
    rodando = store.create("https://b", "video", now=1000)
    store.claim_next(now=1001)
    assert store.get(rodando.id).status in ("pending", "running")
    assert store.list_expirable(cutoff=5000) == []


def test_known_ids_contains_all_statuses(store):
    a = store.create("https://a", "video", now=1000)
    b = store.create("https://b", "video", now=1000)
    store.claim_next(now=1001)
    assert {a.id, b.id} <= store.known_ids()


def test_mark_expired_and_delete_older_than(store):
    job = store.create("https://a", "video", now=1000)
    store.claim_next(now=1001)
    store.mark_ready(job.id, "a.mp4", 10)
    store.mark_expired(job.id)
    assert store.get(job.id).status == EXPIRED
    assert store.delete_older_than(cutoff=5000) == 1
    assert store.get(job.id) is None


def test_reopening_store_keeps_data(tmp_path):
    caminho = tmp_path / "p.db"
    job = Store(caminho).create("https://a", "video", now=1000)
    assert Store(caminho).get(job.id) is not None
