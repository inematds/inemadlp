import json

import pytest
from yt_dlp.cookies import YoutubeDLCookieJar

from inemadlp import cookies

VALIDO = (
    "# Netscape HTTP Cookie File\n"
    ".youtube.com\tTRUE\t/\tTRUE\t1800000000\tSID\tabc123\n"
    "#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t1800000000\tHSID\tdef456\n"
    "\n"
)

# Linha exata do bug reportado: domínio com ponto inicial mas domain_specified=FALSE.
# http.cookiejar._really_load assert domain_specified == initial_dot, e isso derruba
# o carregamento do arquivo INTEIRO (não só essa linha).
LINHA_BUG_MSN = ".assets.msn.com\tFALSE\t/service/segments/recoitems\tFALSE\t0\t_C_Auth\t"


def test_save_writes_and_counts(tmp_path):
    destino = tmp_path / "cookies.txt"
    resultado = cookies.save(VALIDO, destino)
    assert resultado.cookies == 2
    assert resultado.corrigidos == 0
    assert resultado.descartados == 0
    assert destino.read_text() == VALIDO


def test_save_rejects_garbage(tmp_path):
    destino = tmp_path / "cookies.txt"
    with pytest.raises(cookies.InvalidCookieFile):
        cookies.save("isto nao e um cookies.txt", destino)
    assert not destino.exists()


def test_save_rejects_empty(tmp_path):
    with pytest.raises(cookies.InvalidCookieFile):
        cookies.save("# Netscape HTTP Cookie File\n", tmp_path / "cookies.txt")


def test_failed_save_keeps_previous_file(tmp_path):
    destino = tmp_path / "cookies.txt"
    cookies.save(VALIDO, destino)
    with pytest.raises(cookies.InvalidCookieFile):
        cookies.save("lixo", destino)
    assert destino.read_text() == VALIDO


def test_save_leaves_no_temp_files(tmp_path):
    destino = tmp_path / "cookies.txt"
    cookies.save(VALIDO, destino)
    assert [p.name for p in tmp_path.iterdir()] == ["cookies.txt"]


def test_last_updated(tmp_path):
    destino = tmp_path / "cookies.txt"
    assert cookies.last_updated(destino) is None
    cookies.save(VALIDO, destino)
    assert isinstance(cookies.last_updated(destino), int)


def test_save_rejects_missing_netscape_header(tmp_path):
    """Isolates the header requirement: valid 7-field cookie line without header must be rejected."""
    destino = tmp_path / "cookies.txt"
    sem_cabecalho = ".youtube.com\tTRUE\t/\tTRUE\t1800000000\tSID\tabc123\n"
    with pytest.raises(cookies.InvalidCookieFile):
        cookies.save(sem_cabecalho, destino)
    assert not destino.exists()


def test_save_repairs_bug_line_and_result_loads_cleanly(tmp_path):
    """A linha exata do bug relatado, misturada com bons cookies do YouTube: antes do fix
    era aceita crua e derrubava o carregamento inteiro no yt-dlp; depois do fix deve ser
    reparada (domain_specified -> TRUE) e o arquivo salvo deve carregar sem erro."""
    destino = tmp_path / "cookies.txt"
    conteudo = (
        "# Netscape HTTP Cookie File\n"
        ".youtube.com\tTRUE\t/\tTRUE\t1800000000\tSID\tabc123\n"
        "#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t1800000000\tHSID\tdef456\n"
        f"{LINHA_BUG_MSN}\n"
    )
    resultado = cookies.save(conteudo, destino)
    assert resultado.cookies == 3
    assert resultado.corrigidos == 1
    assert resultado.descartados == 0

    # A prova que importa: o arquivo salvo carrega sem lançar exceção no yt-dlp.
    jar = YoutubeDLCookieJar(str(destino))
    jar.load(ignore_discard=True, ignore_expires=True)
    dominios = {c.domain for c in jar}
    assert ".assets.msn.com" in dominios
    assert ".youtube.com" in dominios


def test_save_repairs_domain_without_dot_and_true_flag(tmp_path):
    """Domínio SEM ponto inicial mas com domain_specified=TRUE é reparado no sentido oposto."""
    destino = tmp_path / "cookies.txt"
    conteudo = (
        "# Netscape HTTP Cookie File\n"
        "exemplo.com\tTRUE\t/\tFALSE\t1800000000\tFOO\tbar\n"
    )
    resultado = cookies.save(conteudo, destino)
    assert resultado.cookies == 1
    assert resultado.corrigidos == 1
    assert resultado.descartados == 0
    assert "exemplo.com\tFALSE\t/\tFALSE\t1800000000\tFOO\tbar" in destino.read_text()

    jar = YoutubeDLCookieJar(str(destino))
    jar.load(ignore_discard=True, ignore_expires=True)
    assert {c.domain for c in jar} == {"exemplo.com"}


def test_save_drops_line_with_non_numeric_expiry(tmp_path):
    """Linha com expiry não-numérico é descartada; o resto sobrevive e a contagem reflete isso."""
    destino = tmp_path / "cookies.txt"
    conteudo = (
        "# Netscape HTTP Cookie File\n"
        ".youtube.com\tTRUE\t/\tTRUE\t1800000000\tSID\tabc123\n"
        ".ruim.com\tTRUE\t/\tTRUE\tnao-e-numero\tBAD\tvalor\n"
    )
    resultado = cookies.save(conteudo, destino)
    assert resultado.cookies == 1
    assert resultado.descartados == 1
    assert "BAD" not in destino.read_text()
    assert "SID" in destino.read_text()

    jar = YoutubeDLCookieJar(str(destino))
    jar.load(ignore_discard=True, ignore_expires=True)
    assert {c.name for c in jar} == {"SID"}


def test_save_accepts_json_array_export(tmp_path):
    destino = tmp_path / "cookies.txt"
    dados_json = json.dumps(
        [
            {
                "domain": ".youtube.com",
                "name": "SID",
                "value": "abc123",
                "path": "/",
                "secure": True,
                "httpOnly": True,
                "expirationDate": 1800000000.5,
            },
            {
                "domain": "www.youtube.com",
                "name": "VISIT",
                "value": "xyz",
                "path": "/",
                "secure": False,
                "httpOnly": False,
                "expirationDate": 1800000001,
            },
            {
                "domain": ".youtube.com",
                "name": "SESSIONID",
                "value": "sess",
                "path": "/",
                "secure": True,
                "httpOnly": False,
            },
        ]
    )
    resultado = cookies.save(dados_json, destino)
    assert resultado.cookies == 3

    jar = YoutubeDLCookieJar(str(destino))
    jar.load(ignore_discard=True, ignore_expires=True)
    nomes = {c.name for c in jar}
    assert nomes == {"SID", "VISIT", "SESSIONID"}


def test_save_accepts_json_object_with_cookies_key(tmp_path):
    destino = tmp_path / "cookies.txt"
    dados_json = json.dumps(
        {
            "cookies": [
                {"domain": ".youtube.com", "name": "SID", "value": "abc123"},
                {"domain": ".youtube.com", "name": "HSID", "value": "def456", "httpOnly": True},
            ]
        }
    )
    resultado = cookies.save(dados_json, destino)
    assert resultado.cookies == 2

    jar = YoutubeDLCookieJar(str(destino))
    jar.load(ignore_discard=True, ignore_expires=True)
    assert {c.name for c in jar} == {"SID", "HSID"}


def test_save_rejects_malformed_json(tmp_path):
    destino = tmp_path / "cookies.txt"
    with pytest.raises(cookies.InvalidCookieFile, match="JSON"):
        cookies.save('[{"domain": ".x.com", "name": "A"', destino)
    assert not destino.exists()


def test_save_rejects_html_page(tmp_path):
    destino = tmp_path / "cookies.txt"
    with pytest.raises(cookies.InvalidCookieFile, match="HTML"):
        cookies.save("<!DOCTYPE html><html><body>login</body></html>", destino)
    assert not destino.exists()


def test_save_rejects_space_separated_fields(tmp_path):
    destino = tmp_path / "cookies.txt"
    conteudo = (
        "# Netscape HTTP Cookie File\n"
        ".youtube.com TRUE / TRUE 1800000000 SID abc123\n"
    )
    with pytest.raises(cookies.InvalidCookieFile, match="TAB"):
        cookies.save(conteudo, destino)
    assert not destino.exists()


def test_save_rejects_empty_content(tmp_path):
    destino = tmp_path / "cookies.txt"
    with pytest.raises(cookies.InvalidCookieFile, match="vazio"):
        cookies.save("   \n\n", destino)
    assert not destino.exists()


def test_save_all_lines_unusable_raises_and_keeps_previous_file(tmp_path):
    """Arquivo cujas linhas são TODAS inutilizáveis levanta InvalidCookieFile e não toca
    num cookies.txt anterior já existente."""
    destino = tmp_path / "cookies.txt"
    cookies.save(VALIDO, destino)

    conteudo_ruim = (
        "# Netscape HTTP Cookie File\n"
        "campo1\tcampo2\tcampo3\n"  # menos de 7 campos
        ".outro.com\tTRUE\t/\tTRUE\tnao-numero\tX\tY\n"  # expiry não-numérico
    )
    with pytest.raises(cookies.InvalidCookieFile):
        cookies.save(conteudo_ruim, destino)
    assert destino.read_text() == VALIDO


def test_save_rejects_header_only_export(tmp_path):
    """Export que rodou mas nao capturou nada: so o cabecalho veio."""
    so_cabecalho = (
        "# Netscape HTTP Cookie File\n"
        "# https://curl.haxx.se/rfc/cookie_spec.html\n"
        "# This is a generated file! Do not edit.\n"
    )
    with pytest.raises(cookies.InvalidCookieFile) as erro:
        cookies.save(so_cabecalho, tmp_path / "cookies.txt")
    mensagem = str(erro.value)
    assert "só tem o cabeçalho" in mensagem
    assert "logada" in mensagem
