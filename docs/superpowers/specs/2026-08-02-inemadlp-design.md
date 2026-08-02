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
- Autenticação por senha única, sessão que não expira.
- Atualização dos cookies por upload na própria UI, mais um script de atalho na
  máquina Linux.

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
| Cookies do navegador logado | IPs de datacenter são desafiados pelo YouTube e por outras fontes. Proxy residencial custa por GB — inviável para vídeo. Cookies de um navegador logado resolvem por um custo de manutenção baixo. |
| Cookies enviados por upload na UI, não por `scp` | O PC principal é Windows com Edge/Chrome, e desde a versão 127 esses navegadores cifram os cookies com App-Bound Encryption — extração por script não funciona mais. Upload de um `cookies.txt` exportado por extensão funciona em qualquer SO, e ainda dispensa chave SSH. |
| Senha em texto puro no `.env` | VPS privada, um usuário, arquivo `600`: quem lê o arquivo já é root. Um hash não protegeria nada e só criaria fricção para trocar a senha. |
| Sessão sem expiração | Uso pessoal: logar uma vez no celular e nunca mais. A chave de assinatura é independente da senha, então trocar a senha não desloga (decisão explícita do usuário). |
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
                          ├── /api/cookies          POST recebe cookies.txt
                          └── worker asyncio        consome a fila
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
              SQLite (jobs)  /data/downloads  cookies.txt

PC Windows (Edge/Chrome) ─ extensão exporta cookies.txt ─► upload pela UI
Máquina Linux ─ sync-cookies.sh (cron semanal) ─ curl ─► POST /api/cookies
```

## Componentes

| Módulo | Responsabilidade | Depende de |
|---|---|---|
| `auth.py` | valida a senha, emite e verifica o cookie de sessão assinado; valida o token do script | env `DLP_PASSWORD`, `DLP_SECRET_KEY` |
| `cookies.py` | recebe, valida o formato Netscape e grava `cookies.txt` | filesystem |
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

1. **Login** — POST `/api/login` com a senha; compara com `DLP_PASSWORD` em tempo
   constante; devolve cookie `HttpOnly`, `Secure`, `SameSite=Lax`, **sem expiração
   prática** (validade de 10 anos). Todo `/api/*` exige o cookie. Trocar a senha
   não invalida sessões existentes: a assinatura usa `DLP_SECRET_KEY`, que é
   independente.
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

## Atualização dos cookies

Dois caminhos para o mesmo endpoint `POST /api/cookies`, que valida o formato
Netscape e grava `/data/cookies.txt` atomicamente (escreve `.tmp` e renomeia, para
nunca deixar o yt-dlp ler um arquivo pela metade).

**Caminho principal — upload pela UI.** No PC Windows (ou no celular), com a
extensão *Get cookies.txt LOCALLY* no Edge/Chrome e a sessão aberta nas fontes:
exporta o `cookies.txt` e envia pela tela "Atualizar cookies" da PWA. Autenticado
pelo cookie de sessão. Funciona em qualquer sistema operacional e dispensa SSH.

Extração por script não é possível no Windows: Chrome e Edge cifram os cookies com
App-Bound Encryption desde a versão 127, e só o próprio processo do navegador obtém
a chave.

**Atalho — `sync-cookies.sh` na máquina Linux.** Extrai do perfil Firefox
`kklk8j7a.default` copiando `cookies.sqlite` junto com `-wal` e `-shm` (sem os dois
últimos, a extração pega dados antigos), converte para Netscape e envia por `curl`
ao mesmo endpoint, autenticando com `DLP_UPLOAD_TOKEN`. Roda por **cron semanal**.

A UI mostra a data da última atualização dos cookies, para o estado nunca ser
adivinhado.

## Deploy

- `docker compose`: um container da aplicação (Python + yt-dlp + ffmpeg) e o Caddy.
- Volume `/data` persistente para SQLite, downloads e `cookies.txt`.
- Caddy cuida do TLS automático num subdomínio.
- Trocar a senha: editar `DLP_PASSWORD` no `.env` ao lado do `docker-compose.yml` e
  rodar `docker compose restart`. Sessões abertas continuam válidas.
- yt-dlp atualizado no boot do container (`pip install -U yt-dlp`), porque quebra
  com frequência quando as fontes mudam.

## Configuração (env)

| Variável | Padrão | Uso |
|---|---|---|
| `DLP_PASSWORD` | — | senha única, texto puro no `.env` (modo `600`) |
| `DLP_SECRET_KEY` | — | assinatura do cookie de sessão; gerada na instalação |
| `DLP_UPLOAD_TOKEN` | — | autentica o `sync-cookies.sh` no `POST /api/cookies`; gerado na instalação |
| `DLP_TTL_HOURS` | `6` | validade do arquivo baixado |
| `DLP_DATA_DIR` | `/data` | raiz de dados |

## Testes

- `downloader` — unitários do mapeamento formato→argumentos do yt-dlp; um teste de
  integração marcado, contra um vídeo curto e estável (Big Buck Bunny).
- `store` — CRUD e transições de estado em SQLite temporário.
- `reaper` — relógio injetado: apaga o que passou do TTL, preserva o resto.
- `auth` — senha certa e errada, cookie forjado, rota protegida sem cookie, token de
  upload certo e errado.
- `cookies` — aceita um `cookies.txt` Netscape válido, rejeita lixo, e a gravação é
  atômica (o arquivo antigo sobrevive se a validação falhar).
- `api` — TestClient do FastAPI: criar → listar → baixar, com downloader falso.

Sem teste automatizado de UI: é uma tela só, verificação manual basta.

## Riscos conhecidos

- O yt-dlp quebra periodicamente quando as fontes mudam; mitigado pelo update no
  boot, mas pode exigir intervenção.
- Cookies expiram; o modo de falha é claro e a UI aponta o conserto.
- Baixar de fontes como o YouTube contraria os termos de serviço delas. Uso pessoal,
  instância privada com senha, nunca aberta ao público.
