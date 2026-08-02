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
    "does not look like a netscape format",
    "invalid netscape format cookies file",
)

# O limite de 1080p é uma preferência, não uma exigência: a VPS (IP de
# datacenter) às vezes recebe do YouTube uma lista de formatos mais estreita
# do que a vista de um IP residencial, mesmo com cookies válidos. Sem uma
# cauda de fallback, o seletor rígido estoura "Requested format is not
# available" quando o formato ideal não existe. A cadeia abaixo mantém a
# preferência ≤1080 primeiro (comportamento normal inalterado) e só afrouxa
# progressivamente se necessário, pra nunca virar erro por causa de uma
# lista de formatos incomum.
_FORMATOS = {
    "video": {
        "format": (
            "bv*[height<=1080]+ba/b[height<=1080]"
            "/bv*+ba/b"
            "/best"
        ),
        "merge_output_format": "mp4",
    },
    "audio": {
        "format": "ba/b/best",
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
        # 1 tentativa só: o projeto existe pra não queimar o IP da VPS em
        # detecção de bot das fontes — bater 4x (retries=3) num bloqueio é
        # o oposto do objetivo.
        "retries": 1,
        "restrictfilenames": True,
    }
    if cookies_path is not None and Path(cookies_path).exists():
        opts["cookiefile"] = str(cookies_path)
    return opts


def is_cookie_error(mensagem: str) -> bool:
    baixa = (mensagem or "").lower()
    return any(marcador in baixa for marcador in COOKIES_EXPIRED_MARKERS)


def is_format_error(mensagem: str) -> bool:
    baixa = (mensagem or "").lower()
    return "requested format is not available" in baixa


def _resumo_formatos_disponiveis(info: dict, limite: int = 12) -> str:
    """Monta uma linha em português com os formatos que o YouTube realmente ofereceu.

    Ignora entradas sem vídeo nem áudio (ex.: storyboards) e limita a
    quantidade de itens listados para a UI continuar legível.
    """
    formatos = info.get("formats") or []
    linhas = []
    for formato in formatos:
        vcodec = formato.get("vcodec") or "none"
        acodec = formato.get("acodec") or "none"
        if vcodec == "none" and acodec == "none":
            continue
        if formato.get("height") is None and acodec == "none":
            continue
        fmt_id = formato.get("format_id", "?")
        ext = formato.get("ext", "?")
        altura = formato.get("height")
        altura_txt = f"{altura}p" if altura else "só áudio"
        linhas.append(f"{fmt_id} ({ext}, {altura_txt}, vcodec={vcodec}, acodec={acodec})")

    if not linhas:
        return "nenhum formato de vídeo/áudio foi listado pelo YouTube"

    truncado = linhas[:limite]
    resumo = "; ".join(truncado)
    if len(linhas) > limite:
        resumo += f"; ... (+{len(linhas) - limite} outros)"
    return resumo


def _pick_output_file(destino: Path, fmt: str) -> Path:
    """Localiza o arquivo de saída pelo formato esperado.

    Restringe aos arquivos com as extensões esperadas (.mp4 para video, .m4a para audio)
    e retorna o maior deles. Descarta fragmentos (.part, .ytdl) de downloads interrompidos.
    Levanta DownloadError se nenhum arquivo candidato for encontrado.
    """
    extensoes = {"video": ".mp4", "audio": ".m4a"}
    ext_esperada = extensoes[fmt]

    candidatos = [
        caminho for caminho in destino.iterdir()
        if caminho.is_file() and caminho.suffix == ext_esperada
    ]
    if not candidatos:
        raise DownloadError(f"o yt-dlp terminou sem produzir arquivo {ext_esperada}")

    return max(candidatos, key=lambda caminho: caminho.stat().st_size)


def _resolve_output_file(info: dict, destino: Path, fmt: str) -> Path:
    """Usa o caminho que o próprio yt-dlp reporta como resultado real do download.

    Isso evita adivinhar pela extensão (ex.: 'b[height<=1080]' sem merge/remux
    pode legitimamente entregar um .webm progressivo, o que _pick_output_file
    rejeitaria por não ser .mp4/.m4a). Cai para _pick_output_file quando a
    informação não está disponível.
    """
    downloads = info.get("requested_downloads") or []
    if downloads:
        caminho = downloads[0].get("filepath")
        if caminho and Path(caminho).is_file():
            return Path(caminho)
    return _pick_output_file(destino, fmt)


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
        try:
            info = ydl.extract_info(url, download=True)
        except DownloadError as erro:
            mensagem = str(erro)
            if is_format_error(mensagem):
                try:
                    info_bruto = ydl.extract_info(url, download=False)
                except DownloadError:
                    info_bruto = None
                resumo = (
                    _resumo_formatos_disponiveis(info_bruto)
                    if info_bruto
                    else "não foi possível obter a lista de formatos"
                )
                raise DownloadError(
                    "Nenhum formato compatível foi encontrado para este vídeo. "
                    f"Formatos disponíveis: {resumo}"
                ) from erro
            raise
        titulo = info.get("title") or url
        on_title(titulo)

    arquivo = _resolve_output_file(info, destino, fmt)
    return DownloadResult(path=arquivo, title=titulo, size=arquivo.stat().st_size)
