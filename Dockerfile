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

# O yt-dlp quebra quando as fontes mudam: atualizar a cada boot.
# A atualizacao nao pode derrubar o servico: se a rede/PyPI falhar, segue
# com a versao ja instalada (mas o erro fica visivel no log).
CMD ["sh", "-c", "pip install --no-cache-dir -q -U yt-dlp || echo 'AVISO: falha ao atualizar yt-dlp, seguindo com a versao instalada' >&2; exec uvicorn inemadlp.api:app --host 0.0.0.0 --port 8000"]
