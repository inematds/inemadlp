import json

import pytest

from inemadlp import transcritor


@pytest.fixture
def audio(tmp_path):
    caminho = tmp_path / "audio.wav"
    caminho.write_bytes(b"conteudo-fake-de-audio")
    return caminho


def test_transcrever_monta_multipart_e_headers(audio):
    capturado = {}

    def post_fn(url, headers, corpo):
        capturado["url"] = url
        capturado["headers"] = headers
        capturado["corpo"] = corpo
        resposta = json.dumps({"text": "ola mundo"}).encode()
        return 200, resposta

    texto = transcritor.transcrever(audio, "chave-secreta", post_fn=post_fn)

    assert texto == "ola mundo"
    assert capturado["url"] == transcritor.API_URL
    assert capturado["headers"]["Authorization"] == "Bearer chave-secreta"
    assert "multipart/form-data" in capturado["headers"]["Content-Type"]
    assert b'name="model"' in capturado["corpo"]
    assert transcritor.MODELO.encode() in capturado["corpo"]
    assert b'filename="audio.wav"' in capturado["corpo"]
    assert b"conteudo-fake-de-audio" in capturado["corpo"]


def test_transcrever_levanta_erro_com_mensagem_da_groq(audio):
    def post_fn(url, headers, corpo):
        return 400, json.dumps({"error": {"message": "arquivo inválido"}}).encode()

    with pytest.raises(transcritor.TranscricaoError) as excinfo:
        transcritor.transcrever(audio, "chave", post_fn=post_fn)
    assert "arquivo inválido" in str(excinfo.value)


def test_transcrever_rate_limit_gera_erro_distinguivel(audio):
    def post_fn(url, headers, corpo):
        return 429, json.dumps({"error": {"message": "too many requests"}}).encode()

    with pytest.raises(transcritor.TranscricaoRateLimitError):
        transcritor.transcrever(audio, "chave", post_fn=post_fn)


def test_rate_limit_429_vira_transcricao_rate_limit_error_com_mensagem(audio):
    def post_fn(url, headers, corpo):
        return 429, json.dumps({"error": {"message": "quota excedida"}}).encode()

    with pytest.raises(transcritor.TranscricaoRateLimitError) as excinfo:
        transcritor.transcrever(audio, "chave", post_fn=post_fn)
    # é subclasse de TranscricaoError -> quem trata só o genérico também pega isto
    assert isinstance(excinfo.value, transcritor.TranscricaoError)
    assert "limite de uso da Groq" in str(excinfo.value)
    assert "quota excedida" in str(excinfo.value)


def test_transcrever_erro_sem_campo_text(audio):
    def post_fn(url, headers, corpo):
        return 200, json.dumps({"nao_e_text": "x"}).encode()

    with pytest.raises(transcritor.TranscricaoError):
        transcritor.transcrever(audio, "chave", post_fn=post_fn)
