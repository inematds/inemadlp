#!/usr/bin/env bash
# Instalador do inemadlp. Gera os segredos, escreve o .env e sobe os containers.
# Uso:  ./instalar.sh            (pergunta o domínio)
#       ./instalar.sh dlp.seu.com
set -euo pipefail

cd "$(dirname "$0")"

amarelo() { printf '\033[33m%s\033[0m\n' "$1"; }
verde()   { printf '\033[32m%s\033[0m\n' "$1"; }
vermelho(){ printf '\033[31m%s\033[0m\n' "$1" >&2; }

echo
amarelo "=== inemadlp — instalação ==="
echo

# ---------------------------------------------------------------- pré-requisitos
if ! command -v docker >/dev/null 2>&1; then
  vermelho "Docker não encontrado. Instale com:"
  vermelho "  curl -fsSL https://get.docker.com | sh"
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  vermelho "O plugin 'docker compose' não está disponível. Atualize o Docker."
  exit 1
fi

gerar_segredo() {
  if command -v python3 >/dev/null 2>&1; then
    python3 -c "import secrets,sys; print(secrets.token_urlsafe(int(sys.argv[1])))" "$1"
  elif command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 "$1" | tr -d '\n=+/' | cut -c1-"$1"
  else
    vermelho "Preciso de python3 ou openssl para gerar os segredos."
    exit 1
  fi
}

# ---------------------------------------------------------------------- domínio
DOMINIO="${1:-}"
if [ -z "$DOMINIO" ]; then
  echo "Qual o domínio onde o inemadlp vai responder?"
  echo "Só o nome, sem https:// e sem barra no fim. Ex.: dlp.inema.club"
  printf 'Domínio: '
  read -r DOMINIO
fi

# limpa erros comuns de digitação em vez de deixar o Caddy quebrar depois
DOMINIO="$(echo "$DOMINIO" | sed -E 's#^https?://##; s#/+$##; s/[[:space:]]//g')"
if [ -z "$DOMINIO" ] || ! echo "$DOMINIO" | grep -qE '^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'; then
  vermelho "Domínio inválido: '$DOMINIO'"
  exit 1
fi

# avisa se o DNS ainda não aponta pra cá — o Caddy não consegue certificado sem isso
if command -v getent >/dev/null 2>&1; then
  IP_DOMINIO="$(getent hosts "$DOMINIO" | awk '{print $1}' | head -1 || true)"
  IP_AQUI="$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || true)"
  if [ -n "$IP_DOMINIO" ] && [ -n "$IP_AQUI" ] && [ "$IP_DOMINIO" != "$IP_AQUI" ]; then
    amarelo "Atenção: $DOMINIO aponta para $IP_DOMINIO, mas esta máquina é $IP_AQUI."
    amarelo "O certificado HTTPS só será emitido quando o DNS apontar para cá."
    printf 'Continuar assim mesmo? [s/N] '
    read -r r; [ "$r" = "s" ] || [ "$r" = "S" ] || exit 1
  elif [ -z "$IP_DOMINIO" ]; then
    amarelo "Atenção: $DOMINIO ainda não resolve no DNS."
    printf 'Continuar assim mesmo? [s/N] '
    read -r r; [ "$r" = "s" ] || [ "$r" = "S" ] || exit 1
  fi
fi

# ------------------------------------------------------------------------- .env
if [ -f .env ]; then
  amarelo "Já existe um .env aqui."
  echo "Sobrescrever gera uma senha NOVA e desloga todas as sessões abertas."
  printf 'Sobrescrever? [s/N] '
  read -r r
  if [ "$r" != "s" ] && [ "$r" != "S" ]; then
    echo "Mantendo o .env atual. Ajustando apenas DLP_DOMAIN para $DOMINIO."
    # substitui a linha em vez de acrescentar outra (duas linhas = a última vence)
    if grep -q '^DLP_DOMAIN=' .env; then
      sed -i "s#^DLP_DOMAIN=.*#DLP_DOMAIN=$DOMINIO#" .env
    else
      printf 'DLP_DOMAIN=%s\n' "$DOMINIO" >> .env
    fi
    # garante que não sobrou duplicata de execuções antigas
    if [ "$(grep -c '^DLP_DOMAIN=' .env)" -gt 1 ]; then
      amarelo "Havia DLP_DOMAIN duplicado no .env — removendo as linhas extras."
      awk '!/^DLP_DOMAIN=/ { print } /^DLP_DOMAIN=/ && !visto { print; visto=1 }' .env > .env.tmp
      mv .env.tmp .env
      chmod 600 .env
    fi
    SENHA=""
  else
    SENHA="$(gerar_segredo 24)"
  fi
else
  SENHA="$(gerar_segredo 24)"
fi

if [ -n "$SENHA" ]; then
  umask 077
  cat > .env <<EOF
# Gerado por instalar.sh — não versionar, não compartilhar.
# A senha abaixo é a única barreira entre a internet e os seus cookies.
DLP_PASSWORD=$SENHA
DLP_SECRET_KEY=$(gerar_segredo 32)
DLP_UPLOAD_TOKEN=$(gerar_segredo 32)
DLP_TTL_HOURS=6
DLP_DATA_DIR=/data
DLP_DOMAIN=$DOMINIO
EOF
  chmod 600 .env
  verde "✓ .env criado (permissão 600)"
fi

# ------------------------------------------------------------------------ subir
echo
echo "Vou construir a imagem e subir os containers. A primeira vez leva alguns minutos."
printf 'Continuar? [S/n] '
read -r r
if [ "$r" = "n" ] || [ "$r" = "N" ]; then
  echo "Ok. Quando quiser: docker compose up --build -d"
  exit 0
fi

docker compose up --build -d --force-recreate

# ---------------------------------------------------------------------- resumo
echo
verde "=== pronto ==="
echo
echo "  Endereço:  https://$DOMINIO"
if [ -n "$SENHA" ]; then
  echo "  Senha:     $SENHA"
  amarelo "  ^ anote agora no seu gerenciador de senhas. Ela também está no .env."
else
  echo "  Senha:     a que já estava no .env (inalterada)"
fi
echo
echo "O certificado HTTPS leva de 10 a 60 segundos para ser emitido."
echo "Acompanhe com:  docker compose logs -f caddy"
echo
echo "Próximos passos:"
echo "  1. abra https://$DOMINIO no celular e entre com a senha"
echo "  2. use 'Adicionar à tela de início'"
echo "  3. envie os cookies pelo painel Cookies (veja o README, seção Cookies)"
echo
echo "O token para o sync-cookies.sh está no .env:"
echo "  grep DLP_UPLOAD_TOKEN .env"
echo
