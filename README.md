# inemadlp

Downloader de vídeos pessoal (FastAPI + yt-dlp) rodando em VPS.

## Cookies

Caminho principal: exporte o `cookies.txt` com a extensão *Get cookies.txt LOCALLY*
(Edge/Chrome) estando logado na fonte, e envie pelo painel "Cookies" da própria
interface. Funciona do Windows, do Linux e do celular.

Atalho na máquina Linux com Firefox logado — cron semanal:

```cron
0 9 * * 1 DLP_URL=https://dlp.seudominio DLP_UPLOAD_TOKEN=... /home/nmaldaner/projetos/inemadlp/sync-cookies.sh
```
