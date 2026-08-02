"""Autenticação: senha única, cookie de sessão assinado, token de upload."""

import hmac

from itsdangerous import BadData, URLSafeSerializer

SESSION_COOKIE = "inemadlp_session"
SESSION_MAX_AGE = 315_360_000  # 10 anos: na prática a sessão não expira
_SALT = "inemadlp-session"
_PAYLOAD = "ok"


def _serializer(secret_key: str) -> URLSafeSerializer:
    return URLSafeSerializer(secret_key, salt=_SALT)


def check_password(dada: str, esperada: str) -> bool:
    return hmac.compare_digest(dada or "", esperada)


def issue_session(secret_key: str) -> str:
    return _serializer(secret_key).dumps(_PAYLOAD)


def is_valid_session(valor: str | None, secret_key: str) -> bool:
    if not valor:
        return False
    try:
        return _serializer(secret_key).loads(valor) == _PAYLOAD
    except BadData:
        return False


def check_upload_token(dado: str | None, esperado: str) -> bool:
    return hmac.compare_digest(dado or "", esperado)
