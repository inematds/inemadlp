"""Recebe um cookies.txt no formato Netscape e o grava sem janela de inconsistência."""

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from yt_dlp.cookies import YoutubeDLCookieJar

_CAMPOS = 7
_CABECALHO_NETSCAPE = "# Netscape HTTP Cookie File"


class InvalidCookieFile(ValueError):
    """O conteúdo enviado não é um cookies.txt no formato Netscape."""


@dataclass
class SaveResult:
    """Resultado do salvamento de um cookies.txt sanitizado."""

    cookies: int
    corrigidos: int
    descartados: int


def _dominio_sem_prefixo(campo: str) -> str:
    if campo.startswith("#HttpOnly_"):
        return campo[len("#HttpOnly_") :]
    return campo


def _sanitizar(conteudo: str) -> tuple[list[str], int, int]:
    """Repara/descarta linhas de cookie. Retorna (linhas_mantidas, corrigidos, descartados)."""
    linhas_saida: list[str] = []
    corrigidos = 0
    descartados = 0
    for linha_bruta in conteudo.splitlines(keepends=True):
        quebra = ""
        linha = linha_bruta
        if linha.endswith("\r\n"):
            linha, quebra = linha[:-2], "\r\n"
        elif linha.endswith("\n"):
            linha, quebra = linha[:-1], "\n"
        crua = linha.strip()
        if not crua or (crua.startswith("#") and not crua.startswith("#HttpOnly_")):
            linhas_saida.append(linha_bruta)
            continue
        campos = linha.split("\t")
        if len(campos) != _CAMPOS:
            descartados += 1
            continue
        dominio, domain_specified, path, secure, expiry, nome, valor = campos
        if expiry != "0" and not expiry.lstrip("-").isdigit():
            descartados += 1
            continue
        dominio_real = _dominio_sem_prefixo(dominio)
        esperado = "TRUE" if dominio_real.startswith(".") else "FALSE"
        if domain_specified != esperado:
            domain_specified = esperado
            corrigidos += 1
        linhas_saida.append(
            "\t".join([dominio, domain_specified, path, secure, expiry, nome, valor]) + quebra
        )
    return linhas_saida, corrigidos, descartados


def save(conteudo: str, destino: Path) -> SaveResult:
    destino = Path(destino)

    linhas = conteudo.splitlines()
    if not any(linha.strip() == _CABECALHO_NETSCAPE for linha in linhas[:5]):
        raise InvalidCookieFile(
            "arquivo sem a linha de cabeçalho obrigatória "
            f"'{_CABECALHO_NETSCAPE}' — o http.cookiejar do Python (usado pelo "
            "yt-dlp) exige essa linha para reconhecer o arquivo como Netscape; "
            "exporte o cookies.txt de novo com uma extensão que gere esse cabeçalho"
        )

    linhas_saneadas, corrigidos, descartados = _sanitizar(conteudo)
    conteudo_saneado = "".join(linhas_saneadas)
    if conteudo_saneado and not conteudo_saneado.endswith("\n"):
        conteudo_saneado += "\n"

    total = sum(
        1
        for linha in linhas_saneadas
        if linha.strip() and (not linha.strip().startswith("#") or linha.strip().startswith("#HttpOnly_"))
    )
    if total == 0:
        raise InvalidCookieFile("nenhum cookie encontrado no arquivo")

    # validação autoritativa: só aceitamos o que o próprio yt-dlp conseguir carregar
    fd_val, temporario_validacao = tempfile.mkstemp(suffix=".tmp")
    try:
        with os.fdopen(fd_val, "w") as arquivo:
            arquivo.write(conteudo_saneado)
        jar = YoutubeDLCookieJar(temporario_validacao)
        try:
            jar.load(ignore_discard=True, ignore_expires=True)
        except Exception as erro:  # noqa: BLE001 - queremos capturar qualquer falha de load
            raise InvalidCookieFile(
                f"cookies.txt inválido após sanitização: {erro}"
            ) from erro
    finally:
        Path(temporario_validacao).unlink(missing_ok=True)

    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, temporario = tempfile.mkstemp(dir=destino.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as arquivo:
            arquivo.write(conteudo_saneado)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, destino)
    except BaseException:
        Path(temporario).unlink(missing_ok=True)
        raise
    return SaveResult(cookies=total, corrigidos=corrigidos, descartados=descartados)


def last_updated(destino: Path) -> int | None:
    destino = Path(destino)
    return int(destino.stat().st_mtime) if destino.exists() else None
