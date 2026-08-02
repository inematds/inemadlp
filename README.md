# inemadlp

Downloader pessoal de vídeo e áudio (FastAPI + yt-dlp) que roda na sua VPS. Você
cola o link pelo celular, a VPS baixa e devolve o arquivo — que se apaga sozinho
depois de 6 horas.

## 📖 Guia de uso

Guia completo (landing + passo a passo): **https://inematds.github.io/inemadlp/guia/**

---

## Índice

1. [As três chaves do `.env`](#as-três-chaves-do-env)
2. [Antes de começar](#antes-de-começar)
3. [Passo a passo do deploy](#passo-a-passo-do-deploy)
4. [Acesso remoto e portas](#acesso-remoto-e-portas)
5. [Depois que subiu: o primeiro download](#depois-que-subiu-o-primeiro-download)
6. [Cookies](#cookies)
7. [Operação do dia a dia](#operação-do-dia-a-dia)
8. [Quando algo dá errado](#quando-algo-dá-errado)

---

## As três chaves do `.env`

O `.env` tem três segredos com papéis **diferentes**. Vale entender antes de
gerar, porque as consequências de vazar ou trocar cada um não são as mesmas.

### `DLP_PASSWORD` — a senha que **você** digita

A única que você usa com as mãos. É a que aparece na tela de login. Você digita
uma vez no celular e nunca mais, porque a sessão não expira.

- **Trocar:** edite a linha e rode `docker compose restart app`. As sessões já
  abertas continuam valendo (isso é intencional — trocar a senha não te desloga).
- **Cuidado:** ela é a única coisa entre a internet e o seu `cookies.txt`, que
  contém a sessão do seu Google/YouTube/Instagram. Não existe bloqueio por
  tentativas erradas, por design. Então ela **precisa ser longa e aleatória**,
  não uma senha que você decora.

### `DLP_SECRET_KEY` — a assinatura do cookie de sessão

Você nunca digita isso. Quando você acerta a senha, o servidor devolve um cookie
assinado com essa chave. A cada requisição ele confere a assinatura para saber
que foi ele mesmo quem emitiu aquele cookie, e não alguém que o inventou.

- **Se vazar:** qualquer um fabrica um cookie válido e entra **sem saber a
  senha**. É tão grave quanto vazar a senha.
- **Se você trocar:** todo mundo desloga, inclusive você. É justamente o botão de
  "derrubar todas as sessões" — use se perder o celular.
- É **independente da senha**, e é por isso que trocar a senha não desloga ninguém.

### `DLP_UPLOAD_TOKEN` — a credencial do script

Serve só para o `sync-cookies.sh`. Ele roda sozinho no cron, sem navegador e sem
sessão, então precisa provar quem é de outro jeito: manda o token no cabeçalho
`X-Upload-Token`.

É uma senha de máquina para **uma única rota** (`POST /api/cookies`). Não lista
jobs, não baixa arquivo, não cria download.

- **Se vazar:** o dano é limitado — dá para substituir o seu `cookies.txt`, o que
  quebraria seus downloads, mas não expõe nada (a rota só recebe, nunca devolve o
  arquivo).
- **Se você trocar:** basta atualizar a linha do cron.

**Resumindo:** senha = você entra · secret key = o servidor te reconhece depois ·
upload token = o script entra sozinho por uma portinha só.

---

## Antes de começar

Você precisa de três coisas prontas:

| O quê | Por quê |
|---|---|
| Uma **VPS Linux** com acesso `ssh` | é onde tudo roda |
| **Docker + Compose** instalados nela | única dependência; ffmpeg e yt-dlp vêm na imagem |
| Um **subdomínio** apontado para o IP da VPS | o Caddy emite o certificado HTTPS sozinho |

Instalar o Docker, se ainda não tiver:

```bash
curl -fsSL https://get.docker.com | sh
```

O DNS precisa estar apontado **antes** de subir. No painel do seu domínio, crie
um registro do tipo A:

```
Tipo   Nome            Valor
A      dlp             203.0.113.10      ← o IP da sua VPS
```

Confira que propagou (pode levar alguns minutos):

```bash
dig +short dlp.seudominio    # tem que responder o IP da VPS
```

---

## Passo a passo do deploy

Tudo abaixo roda **dentro da VPS**, via `ssh`.

### 1. Entrar na VPS e clonar

```bash
ssh usuario@203.0.113.10

git clone https://github.com/inematds/inemadlp.git
cd inemadlp
```

### 2. Gerar os três segredos

Rode os três comandos e **guarde cada saída** — você vai colar no `.env` no passo
seguinte:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(24))"   # → DLP_PASSWORD
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # → DLP_SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # → DLP_UPLOAD_TOKEN
```

A senha do primeiro comando é a que você vai digitar no celular — anote no seu
gerenciador de senhas.

### 3. Preencher o `.env`

```bash
cp .env.example .env
nano .env          # ou vim
```

Deixe assim, com os valores que você acabou de gerar:

```ini
DLP_PASSWORD=<saída do 1º comando>
DLP_SECRET_KEY=<saída do 2º comando>
DLP_UPLOAD_TOKEN=<saída do 3º comando>
DLP_TTL_HOURS=6
DLP_DATA_DIR=/data
DLP_DOMAIN=dlp.seudominio
```

Proteja o arquivo — ele tem os três segredos em texto puro:

```bash
chmod 600 .env
```

### 4. Subir

```bash
docker compose up --build -d
```

A primeira construção leva alguns minutos (baixa Python e ffmpeg). Acompanhe:

```bash
docker compose logs -f
```

Você quer ver o `uvicorn running on http://0.0.0.0:8000` do app e o Caddy
obtendo o certificado. `Ctrl-C` sai dos logs sem derrubar nada.

### 5. Confirmar que está no ar

```bash
curl -I https://dlp.seudominio
```

Um `HTTP/2 200` significa que o Caddy já pegou o certificado e o app responde.
Se der erro de certificado, quase sempre é DNS que ainda não propagou ou a porta
80 fechada — veja a seção seguinte.

---

## Acesso remoto e portas

**Você não configura nada de acesso remoto além do DNS.** O acesso é o próprio
site: você abre `https://dlp.seudominio` de qualquer lugar, no celular ou no
desktop, e entra com a senha. Não tem VPN, não tem túnel, não tem porta
esquisita para lembrar.

### As portas envolvidas

| Porta | Quem usa | Precisa estar aberta? |
|---|---|---|
| **443** | HTTPS — é por onde você usa o inemadlp | **sim** |
| **80** | O Caddy, para emitir/renovar o certificado e redirecionar para o 443 | **sim** (sem ela o HTTPS não é emitido) |
| **22** | Seu `ssh` para administrar a VPS | **sim** |
| 8000 | O app, **só dentro** da rede do Docker | **não** — e não deve ser |

A porta 8000 merece uma nota: no `docker-compose.yml` o serviço `app` usa
`expose`, não `ports`. Isso significa que ele é alcançável **apenas** pelo Caddy,
por dentro da rede interna do Docker. Da internet ele não existe. É isso que
garante que ninguém chegue no serviço pulando o HTTPS e a senha.

### Abrir o firewall

Na maioria das VPS há **dois** firewalls: o do sistema e o do provedor.

No sistema (Ubuntu, com `ufw`):

```bash
sudo ufw allow OpenSSH      # não se tranque para fora
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status              # confira antes de encerrar a sessão ssh
```

No painel do provedor (security group da AWS, firewall da Oracle Cloud, da
DigitalOcean, da Hetzner…), libere as mesmas portas — **22, 80 e 443**. Esse é o
passo mais esquecido: o `ufw` fica certo, o painel bloqueia, e o certificado
nunca é emitido.

### Deixar a VPS mais segura (opcional, recomendado)

Como a máquina agora está exposta, vale endurecer o `ssh`:

```bash
# use chave em vez de senha, e desligue login por senha
sudo nano /etc/ssh/sshd_config
#   PasswordAuthentication no
#   PermitRootLogin no
sudo systemctl restart ssh
```

---

## Depois que subiu: o primeiro download

### 1. Instalar no celular

Abra `https://dlp.seudominio` no navegador do celular, digite a senha e use
**"Adicionar à tela de início"**. Vira um ícone como se fosse um app. A sessão
não expira: você não vai digitar a senha de novo.

### 2. Enviar os cookies

Sem isso, o YouTube provavelmente vai recusar os downloads da sua VPS, porque o
IP é de datacenter. No Edge ou no Chrome, **logado** no YouTube:

1. instale a extensão **Get cookies.txt LOCALLY**;
2. abra o YouTube, clique na extensão e exporte o `cookies.txt`;
3. no inemadlp, abra o painel **Cookies** e envie o arquivo.

O painel passa a mostrar a data do último envio.

### 3. Baixar

Cole a URL, escolha **Vídeo** (MP4, até 1080p) ou **Áudio** (M4A), e envie. O
item aparece na lista como "na fila", vira "baixando NN%" e termina com o título
do vídeo e um botão **Baixar**.

Lembre: o arquivo fica disponível por **6 horas**. Depois disso ele some da VPS e
você precisa enfileirar de novo. Se quiser mais tempo, mude `DLP_TTL_HOURS` no
`.env` e reinicie.

---

## Cookies

**Caminho principal:** exporte com a extensão *Get cookies.txt LOCALLY*
(Edge/Chrome), estando logado na fonte, e envie pelo painel "Cookies" da própria
interface. Funciona do Windows, do Linux e do celular.

Não dá para automatizar isso no Windows: o Edge e o Chrome cifram os cookies com
App-Bound Encryption desde a versão 127, e só o próprio navegador consegue a
chave. Por isso o upload é o caminho, e não um script.

**Quando renovar:** quando um download falhar. A interface avisa
*"cookies expirados"* quando reconhece o motivo, então você não precisa
adivinhar. Na prática os cookies do YouTube duram semanas; Instagram e TikTok
quebram mais rápido.

**Atalho na máquina Linux** com Firefox logado — cron semanal, para quase nunca
ver o erro:

```cron
0 9 * * 1 DLP_URL=https://dlp.seudominio DLP_UPLOAD_TOKEN=... /caminho/para/inemadlp/sync-cookies.sh
```

---

## Operação do dia a dia

```bash
docker compose logs -f app     # ver o que está acontecendo
docker compose restart app     # reinicia e atualiza o yt-dlp
docker compose down            # desliga (os dados em ./data ficam)
docker compose up -d           # liga de novo
```

**Trocar a senha:** edite `DLP_PASSWORD` no `.env` e rode
`docker compose restart app`. As sessões abertas continuam válidas.

**Derrubar todas as sessões** (celular perdido): troque também o
`DLP_SECRET_KEY` e reinicie. Aí todo mundo, você inclusive, precisa logar de novo.

**Atualizar o código:**

```bash
git pull && docker compose up --build -d
```

---

## Quando algo dá errado

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| O site não abre, erro de certificado | DNS não propagou, ou porta 80 fechada | `dig +short dlp.seudominio` e confira o firewall do provedor |
| Download falha com "cookies expirados" | os cookies venceram | exporte e envie de novo; depois reenfileire o link (não há retry automático) |
| Download falha com outra mensagem | a fonte não é suportada, ou a URL está errada | a mensagem crua do yt-dlp aparece na lista |
| O arquivo sumiu | passou o TTL de 6 horas | enfileire de novo, ou aumente `DLP_TTL_HOURS` |
| Job travado em "baixando" após reiniciar | o container reiniciou no meio | ele vira "erro" sozinho no boot; reenfileire |
| Disco enchendo | improvável (há limpeza automática) | `du -sh data/downloads` e `docker compose logs app` |
