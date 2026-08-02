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
CMD ["sh", "-c", "pip install --no-cache-dir -q -U yt-dlp && exec uvicorn inemadlp.api:app --host 0.0.0.0 --port 8000"]
