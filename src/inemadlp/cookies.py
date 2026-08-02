"""Recebe um cookies.txt no formato Netscape e o grava sem janela de inconsistência."""

import json
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


def _expiry_para_netscape(cookie: dict) -> str:
    for chave in ("expirationDate", "expires", "expiry"):
        if chave in cookie and cookie[chave] not in (None, "", -1):
            try:
                return str(int(float(cookie[chave])))
            except (TypeError, ValueError):
                continue
    return "0"


def _cookie_dict_para_linha(cookie: dict) -> str | None:
    if not isinstance(cookie, dict):
        return None
    dominio = cookie.get("domain")
    nome = cookie.get("name")
    valor = cookie.get("value")
    if not dominio or not nome or valor is None:
        return None
    path = cookie.get("path") or "/"
    http_only = bool(cookie.get("httpOnly", cookie.get("httponly", False)))
    secure = "TRUE" if cookie.get("secure") else "FALSE"
    domain_specified = "TRUE" if str(dominio).startswith(".") else "FALSE"
    expiry = _expiry_para_netscape(cookie)
    dominio_saida = f"#HttpOnly_{dominio}" if http_only else str(dominio)
    return "\t".join([dominio_saida, domain_specified, str(path), secure, expiry, str(nome), str(valor)])


def _converter_json(conteudo: str) -> str:
    """Converte o export JSON da extensão (array de cookies, ou {"cookies": [...]}) em Netscape."""
    try:
        dados = json.loads(conteudo)
    except json.JSONDecodeError as erro:
        raise InvalidCookieFile(
            "o arquivo parece estar em formato JSON mas não pôde ser lido "
            f"({erro}) — na extensão, escolha exportar como cookies.txt (formato Netscape)"
        ) from erro

    if isinstance(dados, dict):
        lista = dados.get("cookies")
        if not isinstance(lista, list):
            raise InvalidCookieFile(
                "o JSON foi lido, mas não contém uma lista de cookies reconhecível "
                "(esperado um array, ou um objeto com a chave 'cookies') — exporte "
                "novamente como cookies.txt (formato Netscape) ou confira o export JSON"
            )
    elif isinstance(dados, list):
        lista = dados
    else:
        raise InvalidCookieFile(
            "o JSON foi lido, mas não é uma lista de cookies nem um objeto com "
            "'cookies' — na extensão, escolha exportar como cookies.txt (formato Netscape)"
        )

    linhas = [linha for linha in (_cookie_dict_para_linha(c) for c in lista) if linha]
    if not linhas:
        raise InvalidCookieFile(
            "o JSON foi lido, mas nenhum objeto continha os campos mínimos de um "
            "cookie (domain/name/value) — exporte novamente como cookies.txt (formato Netscape)"
        )
    return _CABECALHO_NETSCAPE + "\n" + "\n".join(linhas) + "\n"


def _campos_separados_por_espaco(conteudo: str) -> bool:
    """Detecta a exportação Netscape defeituosa onde os campos vieram separados por espaço."""
    for linha in conteudo.splitlines():
        crua = linha.strip()
        if not crua or crua.startswith("#"):
            continue
        if "\t" in linha:
            continue
        if len(crua.split()) == _CAMPOS:
            return True
    return False


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

    bruto = conteudo.strip()
    if not bruto:
        raise InvalidCookieFile(
            "o arquivo enviado está vazio — confira se o export da extensão gerou "
            "conteúdo antes de enviar de novo"
        )

    if bruto[0] in "[{":
        conteudo = _converter_json(conteudo)
    elif bruto.startswith("<"):
        raise InvalidCookieFile(
            "o conteúdo parece ser uma página HTML, não uma exportação de cookies "
            "— parece que foi salva a página do navegador em vez do arquivo gerado "
            "pela extensão; use o botão de exportar/baixar da extensão de cookies"
        )

    if _campos_separados_por_espaco(conteudo):
        raise InvalidCookieFile(
            "as linhas do arquivo têm os campos separados por ESPAÇO em vez de "
            "TAB — o formato Netscape exige que os 7 campos sejam separados por "
            "TAB; exporte novamente com a extensão no formato cookies.txt padrão"
        )

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
        examinadas = sum(1 for linha in linhas if linha.strip() and not linha.strip().startswith("#"))
        if examinadas == 0:
            # o export rodou, mas não capturou cookie nenhum: só o cabeçalho veio
            raise InvalidCookieFile(
                "o arquivo só tem o cabeçalho, sem nenhuma linha de cookie — a "
                "exportação não capturou nada. Exporte de novo com a aba do site "
                "aberta e já logada (a sua foto de perfil visível), e confira se a "
                "extensão não está limitada a um site diferente"
            )
        raise InvalidCookieFile(
            f"nenhum cookie aproveitável encontrado ({examinadas} linha(s) "
            "examinada(s) e descartada(s) por não terem os 7 campos esperados ou "
            "por terem um campo de expiração inválido) — confira se o arquivo é "
            "mesmo um cookies.txt no formato Netscape"
        )

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
