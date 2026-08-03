import asyncio
import dataclasses
import subprocess
from pathlib import Path

import pytest

from inemadlp import transcritor, worker
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


@pytest.fixture
def ambiente_com_groq(ambiente):
    store, settings = ambiente
    return store, dataclasses.replace(settings, groq_api_key="chave-fake")


def _convert_falso(origem, destino):
    Path(destino).write_bytes(b"0" * 1000)  # bem abaixo do limite


def _transcribe_falso(caminho, api_key):
    return "texto transcrito"


def test_transcricao_reusa_arquivo_de_origem_sem_baixar(ambiente_com_groq):
    store, settings = ambiente_com_groq
    fonte = store.create("https://a", "video", now=1000)
    store.claim_next(now=1000)
    pasta_fonte = settings.downloads_dir / fonte.id
    pasta_fonte.mkdir(parents=True)
    (pasta_fonte / "v.mp4").write_bytes(b"video")
    store.mark_ready(fonte.id, "v.mp4", 5)

    job = store.create("https://a", "transcricao", now=1001, origem=fonte.id)

    chamou_download = {"sim": False}
    convert_chamado_com = {}

    def download_fn(**kwargs):
        chamou_download["sim"] = True
        raise AssertionError("não deveria baixar de novo")

    def convert_capturando(origem, destino):
        convert_chamado_com["origem"] = Path(origem)
        Path(destino).write_bytes(b"0" * 1000)

    progressos_registrados = []
    set_progress_original = store.set_progress

    def set_progress_espiao(job_id, progress):
        progressos_registrados.append(progress)
        return set_progress_original(job_id, progress)

    store.set_progress = set_progress_espiao

    reivindicado = store.claim_next(now=1002)
    worker._processar_transcricao(
        store, settings, reivindicado,
        download_fn=download_fn, convert_fn=convert_capturando,
        transcribe_fn=_transcribe_falso,
    )
    assert chamou_download["sim"] is False
    # a prova real de reuso: convert_fn tem que ter recebido o arquivo do
    # job de ORIGEM, não um caminho qualquer.
    assert convert_chamado_com["origem"] == pasta_fonte / "v.mp4"
    pronto = store.get(job.id)
    assert pronto.status == READY
    assert pronto.filename == "transcricao.txt"
    assert (pasta_fonte.parent / job.id / "transcricao.txt").read_text() == "texto transcrito"
    # progresso avançou de verdade no caminho de reuso, não ficou congelado
    # em 0 do início ao fim (o bug original: on_progress só era ligado no
    # branch de re-download).
    assert progressos_registrados == [0.0, 40.0, 70.0, 100.0]


def test_transcricao_com_origem_expirada_baixa_de_novo(ambiente_com_groq):
    store, settings = ambiente_com_groq
    fonte = store.create("https://a", "video", now=1000)
    store.claim_next(now=1000)
    store.mark_ready(fonte.id, "v.mp4", 5)  # arquivo nunca existiu no disco -> expirado

    job = store.create("https://a", "transcricao", now=1001, origem=fonte.id)
    store.claim_next(now=1002)

    chamou = {"sim": False}

    def download_fn(**kwargs):
        chamou["sim"] = True
        destino = Path(kwargs["destino"])
        destino.mkdir(parents=True, exist_ok=True)
        arquivo = destino / "a.m4a"
        arquivo.write_bytes(b"audio")
        return DownloadResult(path=arquivo, title="T", size=5)

    worker._processar_transcricao(
        store, settings, store.get(job.id),
        download_fn=download_fn, convert_fn=_convert_falso,
        transcribe_fn=_transcribe_falso,
    )
    assert chamou["sim"] is True
    assert store.get(job.id).status == READY


def test_transcricao_audio_grande_e_rejeitada_sem_chamar_groq(ambiente_com_groq):
    store, settings = ambiente_com_groq
    job = store.create("https://a", "transcricao", now=1000)
    store.claim_next(now=1001)

    def convert_grande(origem, destino):
        Path(destino).write_bytes(b"0" * (worker.LIMITE_BYTES + 1))

    chamou_transcribe = {"sim": False}

    def transcribe_fn(caminho, api_key):
        chamou_transcribe["sim"] = True
        return "nao deveria chegar aqui"

    def download_fn(**kwargs):
        destino = Path(kwargs["destino"])
        destino.mkdir(parents=True, exist_ok=True)
        arquivo = destino / "a.m4a"
        arquivo.write_bytes(b"audio")
        return DownloadResult(path=arquivo, title="T", size=5)

    with pytest.raises(Exception) as excinfo:
        worker._processar_transcricao(
            store, settings, store.get(job.id),
            download_fn=download_fn, convert_fn=convert_grande,
            duration_fn=lambda caminho: 3000.0,
            transcribe_fn=transcribe_fn,
        )
    assert chamou_transcribe["sim"] is False
    mensagem = str(excinfo.value)
    assert "longo demais" in mensagem
    assert f"{worker.LIMITE_MINUTOS_APROX} minutos" in mensagem
    assert "~50 min" in mensagem  # 3000s = 50 min, vem de duration_fn


def test_transcricao_sucesso_via_run_one(ambiente_com_groq):
    store, settings = ambiente_com_groq
    job = store.create("https://a", "transcricao", now=1000)

    def download_fn(**kwargs):
        destino = Path(kwargs["destino"])
        destino.mkdir(parents=True, exist_ok=True)
        arquivo = destino / "a.m4a"
        arquivo.write_bytes(b"audio")
        return DownloadResult(path=arquivo, title="T", size=5)

    import inemadlp.worker as worker_mod
    original = worker_mod._processar_transcricao

    def _wrapped(store, settings, job, download_fn=download_fn, **kwargs):
        return original(
            store, settings, job, download_fn=download_fn,
            convert_fn=_convert_falso, transcribe_fn=_transcribe_falso,
        )

    worker_mod._processar_transcricao = _wrapped
    try:
        assert worker.run_one(store, settings, now=1001, download_fn=download_fn) is True
    finally:
        worker_mod._processar_transcricao = original

    pronto = store.get(job.id)
    assert pronto.status == READY
    assert pronto.filename == "transcricao.txt"


def test_transcricao_sem_chave_groq_vira_erro(ambiente):
    store, settings = ambiente  # sem groq_api_key
    store.create("https://a", "transcricao", now=1000)
    assert worker.run_one(store, settings, now=1001, download_fn=_download_falso) is True
    job = store.list_all()[0]
    assert job.status == ERROR
    assert "GROQ_API_KEY" in job.error


@pytest.fixture
def audio_gerado(tmp_path):
    """5s de áudio real (44.1kHz estéreo) gerado com ffmpeg, sem fake nenhum."""
    caminho = tmp_path / "fonte.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
         "-ar", "44100", "-ac", "2", str(caminho)],
        capture_output=True, check=True, timeout=30,
    )
    return caminho


def test_converter_16k_mono_produz_mp3_16khz_mono_de_tamanho_plausivel(audio_gerado, tmp_path):
    destino = tmp_path / "saida.mp3"
    worker._converter_16k_mono(audio_gerado, destino)

    assert destino.exists()
    tamanho = destino.stat().st_size
    # 5s a 64kbit/s -> ~40KB; folga generosa pros cabeçalhos do mp3.
    assert 20_000 < tamanho < 80_000

    sondagem = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=sample_rate,channels,codec_name",
         "-of", "default=noprint_wrappers=1", str(destino)],
        capture_output=True, text=True, check=True, timeout=30,
    )
    saida = sondagem.stdout
    assert "sample_rate=16000" in saida
    assert "channels=1" in saida
    assert "codec_name=mp3" in saida


def test_duracao_segundos_retorna_duracao_real_com_tolerancia(audio_gerado):
    duracao = worker._duracao_segundos(audio_gerado)
    assert duracao is not None
    assert abs(duracao - 5.0) < 0.2


def test_duracao_segundos_arquivo_invalido_retorna_none(tmp_path):
    invalido = tmp_path / "nao_e_audio.txt"
    invalido.write_text("isto não é áudio")
    assert worker._duracao_segundos(invalido) is None


def test_converter_16k_mono_estoura_timeout_vira_transcricao_error(audio_gerado, tmp_path, monkeypatch):
    def run_que_expira(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0] if args else "ffmpeg", timeout=kwargs.get("timeout", 1))

    monkeypatch.setattr(worker.subprocess, "run", run_que_expira)
    destino = tmp_path / "saida.mp3"
    with pytest.raises(transcritor.TranscricaoError) as excinfo:
        worker._converter_16k_mono(audio_gerado, destino)
    assert "demorou demais" in str(excinfo.value)


def test_recover_on_boot_clears_orphans(ambiente):
    store, _ = ambiente
    job = store.create("https://a", "video", now=1000)
    store.claim_next(now=1001)
    assert worker.recover_on_boot(store) == 1
    recuperado = store.get(job.id)
    assert recuperado.status == ERROR
    assert "reiniciado" in recuperado.error
    assert store.create("https://b", "video", now=2000).status == PENDING
