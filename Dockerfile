FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

VOLUME /data
EXPOSE 8000

# O YouTube exige um runtime JS para resolver seus desafios (EJS, ver
# https://github.com/yt-dlp/yt-dlp/wiki/EJS); sem isso o yt-dlp fica sem
# formatos para baixar. yt-dlp[default] traz o suporte a EJS e o pacote
# deno (PyPI) traz o binario do Deno como runtime JS.
#
# O yt-dlp quebra quando as fontes mudam: atualizar a cada boot, junto com
# o suporte a EJS/deno. A atualizacao nao pode derrubar o servico: se a
# rede/PyPI falhar, segue com a versao ja instalada (mas o erro fica
# visivel no log).
CMD ["sh", "-c", "pip install --no-cache-dir -q -U 'yt-dlp[default]' deno || echo 'AVISO: falha ao atualizar yt-dlp/deno, seguindo com a versao instalada' >&2; exec uvicorn inemadlp.api:app --host 0.0.0.0 --port 8000"]
