import base64

from inemadlp import auth

CHAVE = "chave-secreta"


def test_check_password_matches_exactly():
    assert auth.check_password("segredo", "segredo") is True
    assert auth.check_password("Segredo", "segredo") is False
    assert auth.check_password("", "segredo") is False


def test_issued_session_is_valid():
    valor = auth.issue_session(CHAVE)
    assert auth.is_valid_session(valor, CHAVE) is True


def test_session_from_other_key_is_rejected():
    valor = auth.issue_session("outra-chave")
    assert auth.is_valid_session(valor, CHAVE) is False


def test_tampered_or_missing_session_is_rejected():
    valor = auth.issue_session(CHAVE)
    assert auth.is_valid_session(valor + "x", CHAVE) is False
    assert auth.is_valid_session(None, CHAVE) is False
    assert auth.is_valid_session("", CHAVE) is False
    assert auth.is_valid_session("lixo", CHAVE) is False


def test_upload_token():
    assert auth.check_upload_token("tok", "tok") is True
    assert auth.check_upload_token("outro", "tok") is False
    assert auth.check_upload_token(None, "tok") is False


def test_session_lasts_ten_years():
    assert auth.SESSION_MAX_AGE == 315_360_000


def test_corrupted_payload_in_session_is_rejected():
    """Teste que valida se payload corrompido (BadPayload) retorna False.

    Constrói um token com payload inválido (JSON mal formado) mas assinado
    corretamente, forçando BadPayload em vez de BadSignature.
    """
    from itsdangerous import URLSafeSerializer

    serializer = URLSafeSerializer(CHAVE, salt=auth._SALT)
    signer = serializer.make_signer()

    # Cria um payload que é base64 válido mas JSON inválido
    invalid_json = base64.urlsafe_b64encode(b"{invalid").rstrip(b"=").decode()
    signed_token = signer.sign(invalid_json).decode() if isinstance(signer.sign(invalid_json), bytes) else signer.sign(invalid_json)

    # Este token tem assinatura válida mas payload que não pode ser desserializado
    # Deve retornar False (não lançar BadPayload)
    assert auth.is_valid_session(signed_token, CHAVE) is False
