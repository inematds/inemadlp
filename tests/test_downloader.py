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


def test_pick_output_file_ignores_leftover_fragments(tmp_path):
    # Simula um download onde há um fragmento grande (.part) e o arquivo real menor (.mp4)
    arquivo_real = tmp_path / "video.mp4"
    arquivo_real.write_text("x" * 1000)  # 1KB

    arquivo_parte = tmp_path / "video.part"
    arquivo_parte.write_text("x" * 5000)  # 5KB - maior, mas deve ser ignorado

    resultado = downloader._pick_output_file(tmp_path, "video")
    assert resultado == arquivo_real


def test_pick_output_file_raises_when_no_candidate(tmp_path):
    # Cria fragmentos, mas nenhum arquivo final .mp4
    (tmp_path / "video.part").write_text("x" * 100)
    (tmp_path / "video.ytdl").write_text("x" * 100)

    with pytest.raises(downloader.DownloadError, match=".mp4"):
        downloader._pick_output_file(tmp_path, "video")


def test_pick_output_file_for_audio_ignores_non_m4a(tmp_path):
    # Similar para audio: ignora .part e só aceita .m4a
    arquivo_real = tmp_path / "audio.m4a"
    arquivo_real.write_text("x" * 2000)

    arquivo_parte = tmp_path / "audio.part"
    arquivo_parte.write_text("x" * 3000)

    resultado = downloader._pick_output_file(tmp_path, "audio")
    assert resultado == arquivo_real


def test_resolve_output_file_uses_requested_downloads_filepath(tmp_path):
    """FINDING 4: fonte progressiva pode entregar .webm sem merge/remux; o
    caminho autoritativo vem de info['requested_downloads'][0]['filepath'],
    não da extensão adivinhada por _pick_output_file (que só aceita .mp4)."""
    webm = tmp_path / "video.webm"
    webm.write_text("conteudo webm")
    info = {"requested_downloads": [{"filepath": str(webm)}]}

    resultado = downloader._resolve_output_file(info, tmp_path, "video")
    assert resultado == webm


def test_resolve_output_file_falls_back_when_info_missing(tmp_path):
    mp4 = tmp_path / "video.mp4"
    mp4.write_text("conteudo")
    resultado = downloader._resolve_output_file({}, tmp_path, "video")
    assert resultado == mp4


def test_resolve_output_file_falls_back_when_filepath_missing_on_disk(tmp_path):
    mp4 = tmp_path / "video.mp4"
    mp4.write_text("conteudo")
    info = {"requested_downloads": [{"filepath": str(tmp_path / "nao-existe.mkv")}]}
    resultado = downloader._resolve_output_file(info, tmp_path, "video")
    assert resultado == mp4


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
