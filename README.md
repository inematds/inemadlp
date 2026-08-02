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

## Deploy na VPS

```bash
git clone <repo> inemadlp && cd inemadlp
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # DLP_SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # DLP_UPLOAD_TOKEN
# editar o .env: DLP_PASSWORD, as duas chaves acima
chmod 600 .env
echo "DLP_DOMAIN=dlp.seudominio" >> .env
docker compose up --build -d
```

Aponte o DNS do subdomínio para o IP da VPS antes de subir: o Caddy emite o
certificado sozinho no primeiro acesso.

Trocar a senha: editar `DLP_PASSWORD` no `.env` e rodar `docker compose restart app`.
As sessões já abertas continuam válidas.

## Operação

- **Um download falhou dizendo "cookies expirados":** exporte um `cookies.txt` novo
  pela extensão e envie no painel Cookies. Não há retry automático — reenfileire o
  link depois.
- **Arquivo sumiu:** o TTL é de 6 horas (`DLP_TTL_HOURS`). Reenfileire.
- **Logs:** `docker compose logs -f app`.
- **Atualizar o yt-dlp:** `docker compose restart app` (ele atualiza a cada boot).
