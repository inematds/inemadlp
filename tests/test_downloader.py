from pathlib import Path

import pytest

from inemadlp import downloader


def test_video_opts_cap_at_1080_and_remux_mp4(tmp_path):
    opts = downloader.build_opts("video", tmp_path, None)
    assert opts["format"] == "bv*[height<=1080]+ba/b[height<=1080]"
    assert opts["merge_output_format"] == "mp4"
    assert str(tmp_path) in opts["outtmpl"]
    assert "cookiefile" not in opts


def test_audio_opts_extract_m4a(tmp_path):
    opts = downloader.build_opts("audio", tmp_path, None)
    assert opts["format"] == "ba"
    postprocessadores = [p["key"] for p in opts["postprocessors"]]
    assert "FFmpegExtractAudio" in postprocessadores


def test_cookies_included_only_when_file_exists(tmp_path):
    inexistente = tmp_path / "nao-existe.txt"
    assert "cookiefile" not in downloader.build_opts("video", tmp_path, inexistente)
    existente = tmp_path / "cookies.txt"
    existente.write_text("# Netscape HTTP Cookie File\n")
    assert downloader.build_opts("video", tmp_path, existente)["cookiefile"] == str(existente)


def test_unknown_format_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="formato"):
        downloader.build_opts("gif", tmp_path, None)


@pytest.mark.parametrize(
    "mensagem",
    [
        "ERROR: Sign in to confirm you're not a bot",
        "This video requires login",
        "Use --cookies-from-browser or --cookies",
    ],
)
def test_cookie_errors_are_detected(mensagem):
    assert downloader.is_cookie_error(mensagem) is True


def test_other_errors_are_not_cookie_errors():
    assert downloader.is_cookie_error("Unsupported URL: https://exemplo/x") is False


@pytest.mark.integration
def test_downloads_a_real_short_video(tmp_path):
    progresso: list[float] = []
    titulos: list[str] = []
    resultado = downloader.download(
        url="https://www.youtube.com/watch?v=aqz-KE-bpKQ",
        fmt="audio",
        destino=tmp_path,
        cookies_path=None,
        on_progress=progresso.append,
        on_title=titulos.append,
    )
    assert resultado.path.exists()
    assert resultado.size > 0
    assert titulos and progresso
