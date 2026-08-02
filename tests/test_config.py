import pytest

from inemadlp.config import load_settings

BASE_ENV = {
    "DLP_PASSWORD": "segredo",
    "DLP_SECRET_KEY": "chave",
    "DLP_UPLOAD_TOKEN": "token",
}


def test_load_settings_uses_defaults():
    settings = load_settings(BASE_ENV)
    assert settings.ttl_hours == 6
    assert str(settings.data_dir) == "/data"
    assert str(settings.db_path) == "/data/inemadlp.db"
    assert str(settings.downloads_dir) == "/data/downloads"
    assert str(settings.cookies_path) == "/data/cookies.txt"


def test_load_settings_reads_overrides():
    settings = load_settings({**BASE_ENV, "DLP_TTL_HOURS": "24", "DLP_DATA_DIR": "/srv/x"})
    assert settings.ttl_hours == 24
    assert str(settings.downloads_dir) == "/srv/x/downloads"


def test_load_settings_requires_password():
    with pytest.raises(ValueError, match="DLP_PASSWORD"):
        load_settings({"DLP_SECRET_KEY": "chave", "DLP_UPLOAD_TOKEN": "token"})


def test_settings_is_frozen():
    settings = load_settings(BASE_ENV)
    with pytest.raises(Exception):
        settings.ttl_hours = 99
