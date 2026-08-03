"""Rotas HTTP e montagem da PWA."""

import asyncio
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.datastructures import UploadFile as StarletteUploadFile

from inemadlp import __version__, auth, cookies, downloader, worker
from inemadlp.config import Settings, load_settings
from inemadlp.store import READY, Job, Store

WEB_DIR = Path(__file__).parent / "web"
FORMATOS_BASE = ("video", "audio")
FORMATOS_VALIDOS = ("video", "audio", "transcricao")


class LoginBody(BaseModel):
    senha: str


class JobBody(BaseModel):
    url: str
    formato: str
    origem: str | None = None


def _serializar(job: Job, downloads_dir: Path) -> dict:
    dados = {
        "id": job.id,
        "url": job.url,
        "formato": job.format,
        "status": job.status,
        "progresso": job.progress,
        "titulo": job.title,
        "arquivo": job.filename,
        "tamanho": job.size,
        "erro": job.error,
        "erro_de_cookies": bool(job.error) and downloader.is_cookie_error(job.error),
        "criado_em": job.created_at,
    }
    if job.status == READY and job.format == "transcricao" and job.filename:
        caminho = downloads_dir / job.id / job.filename
        if caminho.exists():
            dados["transcricao_texto"] = caminho.read_text(encoding="utf-8", errors="replace")
    return dados


def create_app(settings: Settings, store: Store, start_worker: bool = True) -> FastAPI:
    settings.downloads_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        worker.recover_on_boot(store)
        tarefa = None
        if start_worker:
            tarefa = asyncio.create_task(worker.run_forever(store, settings))
        yield
        if tarefa is not None:
            tarefa.cancel()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)

    def sessao_valida(request: Request) -> bool:
        return auth.is_valid_session(
            request.cookies.get(auth.SESSION_COOKIE), settings.secret_key
        )

    def exigir_sessao(request: Request) -> None:
        if not sessao_valida(request):
            raise HTTPException(status_code=401, detail="não autenticado")

    @app.post("/api/login", status_code=204)
    def login(corpo: LoginBody, response: Response):
        if not auth.check_password(corpo.senha, settings.password):
            raise HTTPException(status_code=401, detail="senha incorreta")
        response.set_cookie(
            auth.SESSION_COOKIE,
            auth.issue_session(settings.secret_key),
            max_age=auth.SESSION_MAX_AGE,
            httponly=True,
            secure=True,
            samesite="lax",
        )

    @app.post("/api/logout", status_code=204)
    def logout(response: Response):
        response.delete_cookie(auth.SESSION_COOKIE)

    @app.get("/api/session")
    def sessao(request: Request):
        return {
            "autenticado": sessao_valida(request),
            "versao": __version__,
            "transcricao_disponivel": bool(settings.groq_api_key),
        }

    @app.get("/api/jobs", dependencies=[Depends(exigir_sessao)])
    def listar():
        return {
            "jobs": [_serializar(job, settings.downloads_dir) for job in store.list_all()],
            "cookies_atualizados_em": cookies.last_updated(settings.cookies_path),
        }

    @app.post("/api/jobs", status_code=201, dependencies=[Depends(exigir_sessao)])
    def criar(corpo: JobBody):
        url = corpo.url.strip()
        if not url:
            raise HTTPException(status_code=400, detail="url vazia")
        if corpo.formato not in FORMATOS_VALIDOS:
            raise HTTPException(status_code=400, detail="formato deve ser video, audio ou transcricao")
        if corpo.formato == "transcricao":
            if not settings.groq_api_key:
                raise HTTPException(
                    status_code=400,
                    detail="transcrição indisponível: nenhuma GROQ_API_KEY configurada no servidor",
                )
            if corpo.origem is not None:
                origem_job = store.get(corpo.origem)
                if origem_job is None:
                    raise HTTPException(status_code=400, detail="job de origem não encontrado")
                if origem_job.format == "transcricao":
                    raise HTTPException(
                        status_code=400,
                        detail="job de origem não pode ser outra transcrição",
                    )
        return {
            "id": store.create(url, corpo.formato, now=int(time.time()), origem=corpo.origem).id
        }

    @app.get("/api/jobs/{job_id}/file", dependencies=[Depends(exigir_sessao)])
    def baixar(job_id: str):
        job = store.get(job_id)
        if job is None or job.status != READY or not job.filename:
            raise HTTPException(status_code=404, detail="arquivo indisponível")
        caminho = settings.downloads_dir / job.id / job.filename
        if not caminho.exists():
            raise HTTPException(status_code=404, detail="arquivo indisponível")
        return FileResponse(caminho, filename=job.filename, media_type="application/octet-stream")

    @app.post("/api/cookies")
    async def enviar_cookies(
        request: Request,
        x_upload_token: str | None = Header(default=None),
    ):
        autorizado = sessao_valida(request) or auth.check_upload_token(
            x_upload_token, settings.upload_token
        )
        if not autorizado:
            raise HTTPException(status_code=401, detail="não autenticado")
        form = await request.form()
        arquivo = form.get("arquivo")
        if not isinstance(arquivo, StarletteUploadFile):
            raise HTTPException(status_code=400, detail="arquivo ausente ou inválido")
        conteudo = (await arquivo.read()).decode("utf-8", errors="replace")
        try:
            resultado = cookies.save(conteudo, settings.cookies_path)
        except cookies.InvalidCookieFile as erro:
            raise HTTPException(status_code=400, detail=str(erro)) from erro
        return {
            "cookies": resultado.cookies,
            "corrigidos": resultado.corrigidos,
            "descartados": resultado.descartados,
        }

    @app.exception_handler(HTTPException)
    async def erro_em_json(request: Request, exc: HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"erro": exc.detail})

    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app


def _build_default_app() -> FastAPI:
    settings = load_settings(os.environ)
    return create_app(settings, Store(settings.db_path))


app = _build_default_app() if os.environ.get("DLP_PASSWORD") else None
