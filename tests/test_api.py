import pytest
from fastapi.testclient import TestClient

import inemadlp
from inemadlp.api import create_app
from inemadlp.config import load_settings
from inemadlp.store import Store

SENHA = "senha-de-teste"
TOKEN = "token-de-teste"
COOKIES_VALIDOS = (
    "# Netscape HTTP Cookie File\n"
    ".youtube.com\tTRUE\t/\tTRUE\t1800000000\tSID\tabc123\n"
)


@pytest.fixture
def ambiente(tmp_path):
    settings = load_settings({
        "DLP_PASSWORD": SENHA,
        "DLP_SECRET_KEY": "chave",
        "DLP_UPLOAD_TOKEN": TOKEN,
        "DLP_DATA_DIR": str(tmp_path),
    })
    store = Store(settings.db_path)
    app = create_app(settings, store, start_worker=False)
    # base_url https: o cookie de sessão é Secure, e http.cookiejar (usado
    # pelo TestClient/httpx) só reenvia cookies Secure em requisições https.
    return TestClient(app, base_url="https://testserver"), store, settings


@pytest.fixture
def logado(ambiente):
    cliente, store, settings = ambiente
    # cliente autenticado próprio: cliente_anonimo (de `ambiente`) precisa
    # continuar sem sessão nos testes que recebem os dois fixtures juntos.
    autenticado = TestClient(cliente.app, base_url="https://testserver")
    assert autenticado.post("/api/login", json={"senha": SENHA}).status_code == 204
    return autenticado, store, settings


def test_login_rejects_wrong_password(ambiente):
    cliente, _, _ = ambiente
    assert cliente.post("/api/login", json={"senha": "errada"}).status_code == 401


def test_api_requires_session(ambiente):
    cliente, _, _ = ambiente
    assert cliente.get("/api/jobs").status_code == 401
    assert cliente.post("/api/jobs", json={"url": "https://a", "formato": "video"}).status_code == 401


def test_session_endpoint_reports_state(ambiente):
    cliente, _, _ = ambiente
    assert cliente.get("/api/session").json()["autenticado"] is False
    cliente.post("/api/login", json={"senha": SENHA})
    assert cliente.get("/api/session").json()["autenticado"] is True


def test_session_endpoint_reports_version(ambiente):
    cliente, _, _ = ambiente
    resposta = cliente.get("/api/session").json()
    assert resposta["versao"] == inemadlp.__version__


def test_logout_clears_session(logado):
    cliente, _, _ = logado
    assert cliente.post("/api/logout").status_code == 204
    assert cliente.get("/api/jobs").status_code == 401


def test_create_and_list_job(logado):
    cliente, _, _ = logado
    resposta = cliente.post("/api/jobs", json={"url": "https://a", "formato": "audio"})
    assert resposta.status_code == 201
    job_id = resposta.json()["id"]
    corpo = cliente.get("/api/jobs").json()
    assert corpo["jobs"][0]["id"] == job_id
    assert corpo["jobs"][0]["status"] == "pending"
    assert corpo["cookies_atualizados_em"] is None


def test_create_job_validates_input(logado):
    cliente, _, _ = logado
    assert cliente.post("/api/jobs", json={"url": "https://a", "formato": "gif"}).status_code == 400
    assert cliente.post("/api/jobs", json={"url": "  ", "formato": "video"}).status_code == 400


def test_cookie_error_is_flagged_in_listing(logado):
    cliente, store, _ = logado
    job = store.create("https://a", "video", now=1000)
    store.mark_error(job.id, "ERROR: Sign in to confirm you're not a bot")
    outro = store.create("https://b", "video", now=1001)
    store.mark_error(outro.id, "ERROR: Unsupported URL")
    por_id = {j["id"]: j for j in cliente.get("/api/jobs").json()["jobs"]}
    assert por_id[job.id]["erro_de_cookies"] is True
    assert por_id[outro.id]["erro_de_cookies"] is False


def test_download_ready_file(logado):
    cliente, store, settings = logado
    job = store.create("https://a", "video", now=1000)
    store.claim_next(now=1001)
    pasta = settings.downloads_dir / job.id
    pasta.mkdir(parents=True)
    (pasta / "video.mp4").write_bytes(b"conteudo-do-video")
    store.mark_ready(job.id, "video.mp4", 17)

    resposta = cliente.get(f"/api/jobs/{job.id}/file")
    assert resposta.status_code == 200
    assert resposta.content == b"conteudo-do-video"
    assert "attachment" in resposta.headers["content-disposition"]


def test_download_missing_or_unready_is_404(logado):
    cliente, store, _ = logado
    assert cliente.get("/api/jobs/nao-existe/file").status_code == 404
    pendente = store.create("https://a", "video", now=1000)
    assert cliente.get(f"/api/jobs/{pendente.id}/file").status_code == 404


def test_cookie_upload_with_session(logado):
    cliente, _, settings = logado
    resposta = cliente.post(
        "/api/cookies",
        files={"arquivo": ("cookies.txt", COOKIES_VALIDOS, "text/plain")},
    )
    assert resposta.status_code == 200
    assert resposta.json()["cookies"] == 1
    assert settings.cookies_path.read_text() == COOKIES_VALIDOS
    assert cliente.get("/api/jobs").json()["cookies_atualizados_em"] is not None


def test_cookie_upload_with_token_and_no_session(ambiente):
    cliente, _, settings = ambiente
    resposta = cliente.post(
        "/api/cookies",
        files={"arquivo": ("cookies.txt", COOKIES_VALIDOS, "text/plain")},
        headers={"X-Upload-Token": TOKEN},
    )
    assert resposta.status_code == 200
    assert settings.cookies_path.exists()


def test_cookie_upload_rejects_bad_credentials_and_content(ambiente, logado):
    cliente_anonimo, _, _ = ambiente
    assert cliente_anonimo.post(
        "/api/cookies",
        files={"arquivo": ("cookies.txt", COOKIES_VALIDOS, "text/plain")},
        headers={"X-Upload-Token": "errado"},
    ).status_code == 401

    cliente, _, _ = logado
    assert cliente.post(
        "/api/cookies",
        files={"arquivo": ("cookies.txt", "lixo", "text/plain")},
    ).status_code == 400


def test_cookie_upload_without_credentials_and_no_body_is_401(ambiente):
    cliente, _, _ = ambiente
    assert cliente.post("/api/cookies").status_code == 401


def test_cookie_upload_with_invalid_token_and_no_body_is_401(ambiente):
    cliente, _, _ = ambiente
    assert cliente.post(
        "/api/cookies",
        headers={"X-Upload-Token": "errado"},
    ).status_code == 401


def test_cookie_upload_missing_file_field_is_400(logado):
    cliente, _, _ = logado
    assert cliente.post("/api/cookies", data={}).status_code == 400


def test_serves_the_pwa(ambiente):
    cliente, _, _ = ambiente
    resposta = cliente.get("/")
    assert resposta.status_code == 200
    assert "inemadlp" in resposta.text.lower()
