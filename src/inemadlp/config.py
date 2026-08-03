"""Leitura do ambiente. Nenhum outro módulo lê variáveis de ambiente."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

_REQUIRED = ("DLP_PASSWORD", "DLP_SECRET_KEY", "DLP_UPLOAD_TOKEN")


@dataclass(frozen=True)
class Settings:
    password: str
    secret_key: str
    upload_token: str
    ttl_hours: int
    data_dir: Path
    groq_api_key: str

    @property
    def db_path(self) -> Path:
        return self.data_dir / "inemadlp.db"

    @property
    def downloads_dir(self) -> Path:
        return self.data_dir / "downloads"

    @property
    def cookies_path(self) -> Path:
        return self.data_dir / "cookies.txt"


def load_settings(env: Mapping[str, str]) -> Settings:
    faltando = [nome for nome in _REQUIRED if not env.get(nome)]
    if faltando:
        raise ValueError(f"variáveis obrigatórias ausentes: {', '.join(faltando)}")
    return Settings(
        password=env["DLP_PASSWORD"],
        secret_key=env["DLP_SECRET_KEY"],
        upload_token=env["DLP_UPLOAD_TOKEN"],
        ttl_hours=int(env.get("DLP_TTL_HOURS", "6")),
        data_dir=Path(env.get("DLP_DATA_DIR", "/data")),
        groq_api_key=env.get("GROQ_API_KEY", ""),
    )
