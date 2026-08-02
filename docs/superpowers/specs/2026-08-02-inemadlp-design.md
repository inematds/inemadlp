# inemadlp — Design

Data: 2026-08-02
Status: aprovado (aguardando plano de implementação)

## Objetivo

Baixador de vídeo/áudio pessoal, no estilo do `baixar_v1.py` do inemavox, acessível
pelo celular e pelo desktop. Roda inteiro numa VPS já contratada. O usuário cola
uma URL, escolhe vídeo ou áudio, e baixa o arquivo. O arquivo é apagado da VPS
depois de um TTL fixo.

Uso estritamente pessoal — um único usuário, protegido por senha.

## Escopo

Dentro:

- Campo de URL + escolha vídeo (MP4, até 1080p) ou áudio (M4A).
- Lista de jobs com status e progresso.
- Download do arquivo pronto, com suporte a retomada (Range).
- Expiração automática dos arquivos.
- PWA instalável na home do celular.
- Autenticação por senha única.
- Sincronização de cookies da máquina local para a VPS.

Fora (YAGNI — cortado explicitamente):

- Escolha fina de resolução (480/720/1440/4K).
- Playlists e canais inteiros.
- Legendas.
- Corte de trechos, transcrição, dublagem (isso é o inemavox).
- Múltiplos usuários, contas, cotas.
- Vercel. A UI é servida pela própria VPS.
- Retry automático de jobs falhos.

## Decisões e justificativas

| Decisão | Razão |
|---|---|
| VPS, não Vercel | Serverless não roda ffmpeg com folga, tem timeout curto, disco efêmero e o egress do arquivo sairia caro. Com VPS própria a Vercel não agrega nada. |
| Cookies da máquina local | IPs de datacenter são desafiados pelo YouTube e por outras fontes. Proxy residencial custa por GB — inviável para vídeo. Cookies do Firefox logado resolvem por um custo de manutenção baixo. |
| TTL fixo (6h) em vez de apagar no download | Tolera download interrompido sem precisar rebaixar da fonte. Um cron burro basta; não precisa detectar fim de resposta HTTP. |
| Monolito FastAPI + SQLite | Uma peça só, yt-dlp é biblioteca Python nativa (progress hook direto), mesmo padrão do inemavox. Redis + worker separado seria over-engineering para um usuário. |
| 1 job por vez | Uso pessoal; concorrência só aumentaria a chance de rate-limit na fonte. |
| Polling em vez de WebSocket | Uma tela, um usuário. Polling de 2s é trivial e suficiente. |

## Arquitetura

```
Celular/Desktop  ──HTTPS──►  Caddy (TLS automático, subdomínio)
                                  │
                                  ▼
                          FastAPI (container único)
                          ├── /                     PWA estático
                          ├── /api/login            senha única → cookie
                          ├── /api/jobs             POST cria, GET lista
                          ├── /api/jobs/{id}/file   entrega o arquivo
                          └── worker asyncio        consome a fila
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
              SQLite (jobs)  /data/downloads  cookies.txt

Máquina local: sync-cookies.sh  ──scp──►  VPS:/data/cookies.txt
```

## Componentes

| Módulo | Responsabilidade | Depende de |
|---|---|---|
| `auth.py` | valida a senha, emite e verifica o cookie de sessão assinado | env `DLP_PASSWORD_HASH`, `DLP_SECRET_KEY` |
| `store.py` | CRUD de jobs e transições de estado no SQLite | sqlite3 |
| `downloader.py` | executa yt-dlp para um job, reporta progresso | yt-dlp, `cookies.txt` |
| `worker.py` | laço: pega job pendente → downloader → atualiza status | store, downloader |
| `reaper.py` | apaga arquivos e jobs além do TTL | store, filesystem |
| `api.py` | rotas HTTP, serve o PWA | todos os acima |
| `web/` | PWA: formulário, lista, polling | nada (fetch puro) |

Cada módulo é testável isolado: `downloader` recebe URL e diretório e devolve um
caminho; `reaper` recebe TTL e um relógio injetado.

## Modelo de dados

Tabela `jobs`:

| Coluna | Tipo | Nota |
|---|---|---|
| `id` | TEXT | UUID4 |
| `url` | TEXT | como o usuário colou |
| `format` | TEXT | `video` \| `audio` |
| `status` | TEXT | `pending` \| `running` \| `ready` \| `error` \| `expired` |
| `progress` | REAL | 0–100, só enquanto `running` |
| `title` | TEXT | título reportado pelo yt-dlp, nulo até saber |
| `filename` | TEXT | nome do arquivo final, nulo até `ready` |
| `size` | INTEGER | bytes, nulo até `ready` |
| `error` | TEXT | mensagem crua do yt-dlp, nulo salvo em `error` |
| `created_at` | INTEGER | epoch segundos |

Arquivos em `/data/downloads/{job_id}/`.

## Fluxo

1. **Login** — POST `/api/login` com a senha; confere contra o hash em env; devolve
   cookie `HttpOnly`, `Secure`, `SameSite=Lax`, validade 30 dias. Todo `/api/*`
   exige o cookie.
2. **Criar job** — POST `/api/jobs` `{url, format}`. Grava `pending`, devolve o id.
   A URL não é validada: quem decide se sabe lidar é o yt-dlp.
3. **Worker** — laço asyncio, um job por vez: `pending` → `running` → yt-dlp com
   `cookies.txt`, saída em `/data/downloads/{job_id}/`, progress hook gravando
   `progress` no SQLite a cada ~1s → `ready` (com `filename`, `size`, `title`) ou
   `error` (com a mensagem).
4. **Status** — o PWA faz GET `/api/jobs` a cada 2s enquanto houver job ativo.
5. **Entrega** — GET `/api/jobs/{id}/file` responde `FileResponse` com
   `Content-Disposition: attachment` e suporte a Range.
6. **Expiração** — tarefa de hora em hora, e também antes de cada job: jobs com
   `created_at` além de `DLP_TTL_HOURS` (padrão 6) têm a pasta apagada e viram
   `expired`. A linha permanece como histórico e é removida do banco após 30 dias.

## Formatos do yt-dlp

- **vídeo**: `bv*[height<=1080]+ba/b[height<=1080]`, remux para MP4.
- **áudio**: `ba`, extração para M4A sem reencode quando a fonte já é AAC.

## Tratamento de erro

- **Cookies expirados / fonte bloqueada** — o job vira `error` com a mensagem crua
  do yt-dlp. Quando a mensagem casa com `Sign in to confirm` ou `login required`,
  a UI mostra: *"Cookies expirados — rode `./sync-cookies.sh` na máquina local"*.
- **URL não suportada** — `error` com a mensagem do yt-dlp. Sem retry.
- **Disco cheio** — o job falha; o reaper roda antes de cada job, não só de hora em
  hora, para liberar espaço primeiro.
- **Restart do container** — jobs em `running` são marcados `error` no boot, para
  não ficarem zumbis. O usuário reenfileira com um clique.
- **Sem retry automático** em nenhum caso: em fonte bloqueada, retry só queima o IP
  mais rápido.

## Sincronização de cookies

`sync-cookies.sh` roda na máquina local: extrai os cookies do perfil Firefox
`kklk8j7a.default` (mesma receita já usada para o Skool), converte para o formato
Netscape `cookies.txt` que o yt-dlp espera, e faz `scp` para `VPS:/data/cookies.txt`.
Execução manual quando um job falhar por bloqueio, ou por cron semanal.

## Deploy

- `docker compose`: um container da aplicação (Python + yt-dlp + ffmpeg) e o Caddy.
- Volume `/data` persistente para SQLite, downloads e `cookies.txt`.
- Caddy cuida do TLS automático num subdomínio.
- yt-dlp atualizado no boot do container (`pip install -U yt-dlp`), porque quebra
  com frequência quando as fontes mudam.

## Configuração (env)

| Variável | Padrão | Uso |
|---|---|---|
| `DLP_PASSWORD_HASH` | — | hash da senha única |
| `DLP_SECRET_KEY` | — | assinatura do cookie de sessão |
| `DLP_TTL_HOURS` | `6` | validade do arquivo baixado |
| `DLP_DATA_DIR` | `/data` | raiz de dados |

## Testes

- `downloader` — unitários do mapeamento formato→argumentos do yt-dlp; um teste de
  integração marcado, contra um vídeo curto e estável (Big Buck Bunny).
- `store` — CRUD e transições de estado em SQLite temporário.
- `reaper` — relógio injetado: apaga o que passou do TTL, preserva o resto.
- `auth` — senha certa e errada, cookie forjado, rota protegida sem cookie.
- `api` — TestClient do FastAPI: criar → listar → baixar, com downloader falso.

Sem teste automatizado de UI: é uma tela só, verificação manual basta.

## Riscos conhecidos

- O yt-dlp quebra periodicamente quando as fontes mudam; mitigado pelo update no
  boot, mas pode exigir intervenção.
- Cookies expiram; o modo de falha é claro e a UI aponta o conserto.
- Baixar de fontes como o YouTube contraria os termos de serviço delas. Uso pessoal,
  instância privada com senha, nunca aberta ao público.
