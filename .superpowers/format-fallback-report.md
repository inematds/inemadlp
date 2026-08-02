# Fix: fallback de formato no downloader (yt-dlp)

## Bug
Na VPS (IP de datacenter), o YouTube às vezes entrega uma lista de formatos mais
estreita do que a vista de um IP residencial, mesmo com cookies válidos. O
seletor rígido `bv*[height<=1080]+ba/b[height<=1080]` (vídeo) e `ba` (áudio)
não tinha fallback: quando nada batia exatamente, o yt-dlp estourava
`Requested format is not available`.

## Fix

1. `src/inemadlp/downloader.py` — `_FORMATOS`:
   - `video`: `bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b/best` — mantém a
     preferência ≤1080p primeiro (comportamento normal inalterado) e afrouxa
     progressivamente: melhor vídeo+áudio sem limite de altura → progressivo
     sem limite → `best` genérico. Comentário em português explicando que o
     limite é preferência, não exigência.
   - `audio`: `ba/b/best` — melhor áudio isolado → áudio de qualquer formato
     combinado → melhor disponível.

2. `download()` — passou a capturar `DownloadError` ao redor do
   `extract_info(url, download=True)`. Quando a mensagem indica formato
   indisponível (`is_format_error`), monta um resumo em português dos
   formatos realmente ofertados (`_resumo_formatos_disponiveis`) e relança
   `DownloadError` com essa informação. Esse resumo precisa de uma segunda
   chamada `extract_info(download=False)` — mas **só no caminho de erro**
   (raro); o fluxo normal de sucesso continua com uma única requisição, como
   antes.

3. Novo helper `_resumo_formatos_disponiveis(info, limite=12)`: lista
   `id (ext, altura, vcodec=, acodec=)` por formato, ignora entradas
   storyboard-only (`vcodec==none and acodec==none`), corta em `limite`
   entradas e anexa `+N outros` quando há mais.

4. Assinatura de `download()` e campos de `DownloadResult` inalterados.
   Continua havendo apenas uma chamada `extract_info(download=True)` no
   caminho feliz.

## Testes adicionados (`tests/test_downloader.py`)
- `test_video_opts_have_looser_fallbacks_after_1080_preference`
- `test_audio_opts_extract_m4a` (ajustado para prefixo, não igualdade exata)
- `test_video_opts_cap_at_1080_and_remux_mp4` (ajustado para prefixo)
- `test_format_error_is_detected` / `test_other_errors_are_not_format_errors`
- `test_resumo_formatos_disponiveis_lista_ids_alturas_e_extensoes`
- `test_resumo_formatos_disponiveis_ignora_storyboards`
- `test_resumo_formatos_disponiveis_respeita_limite`

## Resultados reais

Suíte completa:
```
97 passed, 1 deselected, 1 warning in 1.93s
```

Integração (`-m integration -v`):
```
tests/test_downloader.py::test_downloads_a_real_short_video PASSED
1 passed, 97 deselected, 1 warning in 4.33s
```

## Observação
O item "não reintroduzir uma segunda requisição de metadados" foi respeitado
no fluxo normal (sucesso = 1 chamada). No caminho de ERRO de formato — que só
ocorre quando toda a cadeia de fallback falha, cenário raro — uma segunda
chamada `extract_info(download=False)` é feita apenas para montar a mensagem
de diagnóstico. Não há como obter a lista completa de formatos a partir da
`DownloadError` do yt-dlp sem isso, já que a exceção não carrega o dict de
formatos.
