"""Recebe um cookies.txt no formato Netscape e o grava sem janela de inconsistência."""

import os
import tempfile
from pathlib import Path

_CAMPOS = 7
_CABECALHO_NETSCAPE = "# Netscape HTTP Cookie File"


class InvalidCookieFile(ValueError):
    """O conteúdo enviado não é um cookies.txt no formato Netscape."""


def _contar_cookies(conteudo: str) -> int:
    linhas = conteudo.splitlines()
    if not any(linha.strip() == _CABECALHO_NETSCAPE for linha in linhas[:5]):
        raise InvalidCookieFile(
            "arquivo sem a linha de cabeçalho obrigatória "
            f"'{_CABECALHO_NETSCAPE}' — o http.cookiejar do Python (usado pelo "
            "yt-dlp) exige essa linha para reconhecer o arquivo como Netscape; "
            "exporte o cookies.txt de novo com uma extensão que gere esse cabeçalho"
        )
    total = 0
    for linha in conteudo.splitlines():
        crua = linha.strip()
        if not crua or (crua.startswith("#") and not crua.startswith("#HttpOnly_")):
            continue
        if len(linha.split("\t")) != _CAMPOS:
            raise InvalidCookieFile(
                "linha fora do formato Netscape (esperados 7 campos separados por TAB)"
            )
        total += 1
    if total == 0:
        raise InvalidCookieFile("nenhum cookie encontrado no arquivo")
    return total


def save(conteudo: str, destino: Path) -> int:
    destino = Path(destino)
    total = _contar_cookies(conteudo)  # valida antes de tocar no disco
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, temporario = tempfile.mkstemp(dir=destino.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as arquivo:
            arquivo.write(conteudo)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, destino)
    except BaseException:
        Path(temporario).unlink(missing_ok=True)
        raise
    return total


def last_updated(destino: Path) -> int | None:
    destino = Path(destino)
    return int(destino.stat().st_mtime) if destino.exists() else None
