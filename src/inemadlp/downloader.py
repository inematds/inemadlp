"""Camada fina sobre o yt-dlp: traduz um job em opções e executa o download."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError  # noqa: F401  (reexportado para o worker)

COOKIES_EXPIRED_MARKERS = (
    "sign in to confirm",
    "requires login",
    "login required",
    "private video",
    "--cookies",
    "rate-limit reached",
)

_FORMATOS = {
    "video": {
        "format": "bv*[height<=1080]+ba/b[height<=1080]",
        "merge_output_format": "mp4",
    },
    "audio": {
        "format": "ba",
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "m4a", "preferredquality": "0"}
        ],
    },
}


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    title: str
    size: int


def build_opts(fmt: str, destino: Path, cookies_path: Path | None) -> dict:
    if fmt not in _FORMATOS:
        raise ValueError(f"formato desconhecido: {fmt}")
    opts = {
        **_FORMATOS[fmt],
        "outtmpl": str(Path(destino) / "%(title).150B.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 3,
        "restrictfilenames": True,
    }
    if cookies_path is not None and Path(cookies_path).exists():
        opts["cookiefile"] = str(cookies_path)
    return opts


def is_cookie_error(mensagem: str) -> bool:
    baixa = (mensagem or "").lower()
    return any(marcador in baixa for marcador in COOKIES_EXPIRED_MARKERS)


def download(
    url: str,
    fmt: str,
    destino: Path,
    cookies_path: Path | None,
    on_progress: Callable[[float], None],
    on_title: Callable[[str], None],
) -> DownloadResult:
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    opts = build_opts(fmt, destino, cookies_path)

    def hook(evento: dict) -> None:
        if evento["status"] != "downloading":
            return
        total = evento.get("total_bytes") or evento.get("total_bytes_estimate")
        if total:
            on_progress(round(evento.get("downloaded_bytes", 0) / total * 100, 1))

    opts["progress_hooks"] = [hook]

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        titulo = info.get("title") or url
        on_title(titulo)
        ydl.download([url])

    arquivos = [caminho for caminho in destino.iterdir() if caminho.is_file()]
    if not arquivos:
        raise DownloadError("o yt-dlp terminou sem produzir arquivo")
    arquivo = max(arquivos, key=lambda caminho: caminho.stat().st_size)
    return DownloadResult(path=arquivo, title=titulo, size=arquivo.stat().st_size)
