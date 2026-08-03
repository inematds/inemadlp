#!/usr/bin/env bash
# Atualiza o inemadlp nesta máquina: traz o código novo e reconstrói os containers.
# Uso:  ./atualizar.sh
set -euo pipefail

cd "$(dirname "$0")"

amarelo() { printf '\033[33m%s\033[0m\n' "$1"; }
verde()   { printf '\033[32m%s\033[0m\n' "$1"; }
vermelho(){ printf '\033[31m%s\033[0m\n' "$1" >&2; }

echo
amarelo "=== inemadlp — atualização ==="
echo

if ! command -v docker >/dev/null 2>&1; then
  vermelho "Docker não encontrado nesta máquina."
  exit 1
fi
if [ ! -f .env ]; then
  vermelho "Não achei o .env aqui. Você está na pasta certa? (esperado: a pasta do inemadlp)"
  exit 1
fi

# ------------------------------------------------- edições locais não commitadas
# O .env não conta: ele é git-ignored e nunca aparece aqui.
if ! git diff --quiet || ! git diff --cached --quiet; then
  amarelo "Há edições locais não commitadas nestes arquivos:"
  git diff --name-only HEAD | sed 's/^/  - /'
  echo
  echo "Vou guardá-las com 'git stash' antes de atualizar. Elas NÃO são perdidas:"
  echo "  git stash list     mostra o que foi guardado"
  echo "  git stash pop      traz de volta, se você precisar"
  printf 'Continuar? [S/n] '
  read -r r
  if [ "$r" = "n" ] || [ "$r" = "N" ]; then
    echo "Cancelado. Nada foi alterado."
    exit 0
  fi
  git stash push -m "atualizar.sh $(git rev-parse --short HEAD)"
  verde "✓ edições locais guardadas no stash"
fi

# ----------------------------------------------------------------- código novo
ANTES="$(git rev-parse --short HEAD)"
echo "Buscando atualizações..."
git fetch --quiet origin

if [ "$(git rev-parse HEAD)" = "$(git rev-parse '@{u}' 2>/dev/null || echo HEAD)" ]; then
  verde "Já está na versão mais recente ($ANTES). Nada a fazer."
  echo "Se quiser reconstruir mesmo assim: docker compose up -d --build"
  exit 0
fi

echo
echo "Novidades que vão entrar:"
git --no-pager log --oneline HEAD..'@{u}' | sed 's/^/  /'
echo

# --ff-only: se divergir, para em vez de criar merge silencioso
if ! git merge --ff-only '@{u}'; then
  vermelho "O histórico local divergiu do remoto — não dá para atualizar automaticamente."
  vermelho "Resolva à mão (git status) ou, se puder descartar o local: git reset --hard @{u}"
  exit 1
fi
DEPOIS="$(git rev-parse --short HEAD)"
verde "✓ código atualizado: $ANTES → $DEPOIS"

# -------------------------------------------------------------- reconstruir
echo
echo "Reconstruindo a imagem e recriando os containers..."
docker compose up -d --build

echo
docker compose ps

# ------------------------------------------------------------------ conferir
DOMINIO="$(grep -E '^DLP_DOMAIN=' .env | tail -1 | cut -d= -f2- | tr -d '"'"'"' ' || true)"
if [ -n "$DOMINIO" ]; then
  echo
  echo "Conferindo https://$DOMINIO ..."
  for i in 1 2 3 4 5 6; do
    CODIGO="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "https://$DOMINIO/" || true)"
    [ "$CODIGO" = "200" ] && break
    sleep 5
  done
  if [ "${CODIGO:-}" = "200" ]; then
    verde "✓ https://$DOMINIO respondendo (HTTP $CODIGO)"
  else
    amarelo "Ainda não respondeu 200 (último: ${CODIGO:-sem resposta})."
    amarelo "Veja o que houve: docker compose logs --tail=40 app caddy"
  fi
fi

echo
verde "=== atualizado ==="
echo "Logs ao vivo:  docker compose logs -f app     (Ctrl-C sai sem derrubar)"
echo
