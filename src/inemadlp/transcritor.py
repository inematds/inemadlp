"""Fala com a API da Groq (Whisper) para transcrever áudio. Único módulo que a toca."""

import json
import mimetypes
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from pathlib import Path

API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MODELO = "whisper-large-v3-turbo"


class TranscricaoError(Exception):
    """Groq recusou o pedido ou está fora do ar. A mensagem inclui o motivo dela."""


class TranscricaoRateLimitError(TranscricaoError):
    """Cota/limite de requisições excedido — não é um bug, é o plano da Groq."""


def _corpo_multipart(campos: dict[str, str], arquivo: Path, campo_arquivo: str = "file") -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    partes = []
    for nome, valor in campos.items():
        partes.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{nome}\"\r\n\r\n{valor}\r\n".encode()
        )
    tipo = mimetypes.guess_type(arquivo.name)[0] or "application/octet-stream"
    cabecalho_arquivo = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"{campo_arquivo}\"; "
        f"filename=\"{arquivo.name}\"\r\nContent-Type: {tipo}\r\n\r\n"
    ).encode()
    partes.append(cabecalho_arquivo + arquivo.read_bytes() + b"\r\n")
    partes.append(f"--{boundary}--\r\n".encode())
    return b"".join(partes), boundary


def _post_real(url: str, headers: dict, corpo: bytes) -> tuple[int, bytes]:
    requisicao = urllib.request.Request(url, data=corpo, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(requisicao, timeout=300) as resposta:
            return resposta.status, resposta.read()
    except urllib.error.HTTPError as erro:
        return erro.code, erro.read()


def transcrever(
    audio_path: Path,
    api_key: str,
    post_fn: Callable[[str, dict, bytes], tuple[int, bytes]] = _post_real,
) -> str:
    """Envia o áudio para a Groq e retorna o texto transcrito.

    post_fn recebe (url, headers, corpo) e devolve (status_code, corpo_bytes) —
    ponto de injeção para os testes não baterem na rede de verdade.
    """
    audio_path = Path(audio_path)
    corpo, boundary = _corpo_multipart({"model": MODELO}, audio_path)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        # Sem User-Agent explícito, o Cloudflare da Groq bloqueia o urllib
        # padrão do Python (erro 1010).
        "User-Agent": "inemadlp/1.1.0 (+https://github.com/inematds/inemadlp)",
    }
    status, resposta_bytes = post_fn(API_URL, headers, corpo)

    try:
        dados = json.loads(resposta_bytes.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        dados = {}

    if status == 429:
        mensagem = (dados.get("error") or {}).get("message") if isinstance(dados, dict) else None
        raise TranscricaoRateLimitError(
            "limite de uso da Groq foi atingido — não é um erro do sistema, é a cota "
            f"do plano configurado; tente novamente mais tarde"
            + (f" ({mensagem})" if mensagem else "")
        )

    if status != 200:
        mensagem = None
        if isinstance(dados, dict):
            mensagem = (dados.get("error") or {}).get("message")
        raise TranscricaoError(
            f"a Groq recusou a transcrição (HTTP {status})" + (f": {mensagem}" if mensagem else "")
        )

    texto = dados.get("text") if isinstance(dados, dict) else None
    if texto is None:
        raise TranscricaoError("a Groq respondeu 200 mas sem o campo 'text' esperado")
    return texto
