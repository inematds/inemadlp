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
