"""Laço que consome a fila. Um job por vez."""

import asyncio
import logging
import subprocess
import time
from pathlib import Path

from inemadlp import downloader, reaper, transcritor
from inemadlp.config import Settings
from inemadlp.store import READY, Store

logger = logging.getLogger(__name__)

BOOT_MESSAGE = "o serviço foi reiniciado durante o download"

# Limite deliberado: sem chunking automático. 25 MB em 16kHz/mono/16-bit
# equivale a pouco mais de 50 minutos de áudio.
LIMITE_BYTES = 25 * 1024 * 1024
LIMITE_MINUTOS_APROX = 50


def recover_on_boot(store: Store) -> int:
    return store.reset_running_to_error(BOOT_MESSAGE)


def _converter_16k_mono(origem: Path, destino: Path) -> None:
    resultado = subprocess.run(
        ["ffmpeg", "-i", str(origem), "-ar", "16000", "-ac", "1", "-y", str(destino)],
        capture_output=True,
        text=True,
    )
    if resultado.returncode != 0:
        raise RuntimeError(f"ffmpeg falhou ao converter o áudio: {resultado.stderr[-500:]}")


def _duracao_segundos(caminho: Path) -> float | None:
    resultado = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(caminho),
        ],
        capture_output=True,
        text=True,
    )
    try:
        return float(resultado.stdout.strip())
    except (ValueError, AttributeError):
        return None


def _arquivo_origem_disponivel(store: Store, settings: Settings, origem_id: str) -> Path | None:
    origem_job = store.get(origem_id)
    if origem_job is None or origem_job.status != READY or not origem_job.filename:
        return None
    caminho = settings.downloads_dir / origem_job.id / origem_job.filename
    return caminho if caminho.exists() else None


def _processar_transcricao(
    store: Store,
    settings: Settings,
    job,
    download_fn=downloader.download,
    convert_fn=_converter_16k_mono,
    duration_fn=_duracao_segundos,
    transcribe_fn=transcritor.transcrever,
) -> None:
    destino = settings.downloads_dir / job.id
    destino.mkdir(parents=True, exist_ok=True)

    if not settings.groq_api_key:
        raise transcritor.TranscricaoError(
            "transcrição indisponível: nenhuma GROQ_API_KEY configurada no servidor"
        )

    audio_original: Path | None = None
    if job.origem:
        audio_original = _arquivo_origem_disponivel(store, settings, job.origem)

    if audio_original is None:
        # origem ausente, sem status ready, ou arquivo já expirado: baixa de novo.
        resultado = download_fn(
            url=job.url,
            fmt="audio",
            destino=destino,
            cookies_path=settings.cookies_path,
            on_progress=lambda pct: store.set_progress(job.id, pct),
            on_title=lambda titulo: store.set_title(job.id, titulo),
        )
        audio_original = resultado.path
        store.set_title(job.id, resultado.title)

    convertido = destino / "audio_16k_mono.wav"
    convert_fn(audio_original, convertido)

    tamanho = convertido.stat().st_size
    if tamanho > LIMITE_BYTES:
        duracao = duration_fn(convertido)
        duracao_txt = f"~{round(duracao / 60)} min" if duracao else "duração desconhecida"
        raise transcritor.TranscricaoError(
            f"áudio longo demais para transcrever ({duracao_txt}) — o limite é de "
            f"aproximadamente {LIMITE_MINUTOS_APROX} minutos por job, sem divisão automática"
        )

    texto = transcribe_fn(convertido, settings.groq_api_key)

    nome_txt = "transcricao.txt"
    (destino / nome_txt).write_text(texto, encoding="utf-8")
    store.mark_ready(job.id, nome_txt, len(texto.encode("utf-8")))


def run_one(store: Store, settings: Settings, now: int, download_fn=downloader.download) -> bool:
    # Libera espaço antes de baixar: disco cheio é um modo de falha real.
    # Uma falha no reap não pode impedir o processamento do job — só loga e segue.
    try:
        reaper.reap(store, settings.downloads_dir, settings.ttl_hours, now)
    except Exception as erro:
        logger.warning("reap falhou: %s", erro)

    try:
        job = store.claim_next(now=now)
    except Exception as erro:
        logger.warning("claim_next falhou: %s", erro)
        return False

    if job is None:
        return False

    if job.format == "transcricao":
        try:
            _processar_transcricao(store, settings, job, download_fn=download_fn)
        except Exception as erro:
            logger.warning("job %s falhou: %s", job.id, erro)
            store.mark_error(job.id, str(erro))
        return True

    try:
        resultado = download_fn(
            url=job.url,
            fmt=job.format,
            destino=settings.downloads_dir / job.id,
            cookies_path=settings.cookies_path,
            on_progress=lambda pct: store.set_progress(job.id, pct),
            on_title=lambda titulo: store.set_title(job.id, titulo),
        )
        # mark_ready fica dentro do bloco protegido: um job já reivindicado
        # precisa terminar em estado terminal, nunca ficar preso em "running".
        store.mark_ready(job.id, resultado.path.name, resultado.size)
    except Exception as erro:  # inclusive DownloadError: nada derruba o worker
        logger.warning("job %s falhou: %s", job.id, erro)
        store.mark_error(job.id, str(erro))
        return True

    return True


async def run_forever(store: Store, settings: Settings, sleep_seconds: float = 2.0) -> None:
    while True:
        try:
            # O to_thread bloqueia até o fim da iteração: se um cancel chegar
            # durante um download em andamento, o cancelamento só é efetivo
            # entre jobs — limitação aceita, não há como interromper a
            # chamada bloqueante de download_fn no meio do caminho.
            processou = await asyncio.to_thread(run_one, store, settings, int(time.time()))
        except asyncio.CancelledError:
            raise
        except Exception as erro:
            logger.warning("iteração do worker falhou: %s", erro)
            processou = False
        if not processou:
            await asyncio.sleep(sleep_seconds)
