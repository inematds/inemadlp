import pytest

from inemadlp import cookies

VALIDO = (
    "# Netscape HTTP Cookie File\n"
    ".youtube.com\tTRUE\t/\tTRUE\t1800000000\tSID\tabc123\n"
    "#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t1800000000\tHSID\tdef456\n"
    "\n"
)


def test_save_writes_and_counts(tmp_path):
    destino = tmp_path / "cookies.txt"
    assert cookies.save(VALIDO, destino) == 2
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
    # Perfectly well-formed Netscape cookie format (7 TAB-separated fields)
    # but WITHOUT the required "# Netscape HTTP Cookie File" header line.
    # This input would have been accepted by the pre-fix code.
    sem_cabecalho = ".youtube.com\tTRUE\t/\tTRUE\t1800000000\tSID\tabc123\n"
    with pytest.raises(cookies.InvalidCookieFile):
        cookies.save(sem_cabecalho, destino)
    assert not destino.exists()
