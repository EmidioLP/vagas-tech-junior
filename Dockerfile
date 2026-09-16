# Imagem da API. O scraper nao roda aqui: portais de vaga costumam bloquear IP
# de nuvem. No Docker Compose, os dados chegam pelo snapshot em seed/, carregado
# no historico depois das migrations.
FROM python:3.11-slim

# PYTHONUNBUFFERED: sem isso o log do uvicorn fica preso no buffer e o
# `docker compose logs` so mostra as mensagens quando o processo termina.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# As dependencias entram antes do codigo para o cache de camadas do Docker
# sobreviver a cada alteracao em .py -- sem isso todo build reinstalaria tudo.
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# So o que a API precisa. `scraper/` entra porque a API le os YAMLs de regras
# (areas e tecnologias) de la. `persistence/` guarda a consulta da foto atual e a
# gravacao que a carga do seed usa. `alembic.ini`, `migrations/`, `scripts/` e
# `seed/` sao o que o compose roda no boot.
COPY alembic.ini ./
COPY migrations/ ./migrations/
COPY api/ ./api/
COPY persistence/ ./persistence/
COPY scraper/ ./scraper/
COPY scripts/ ./scripts/
COPY seed/ ./seed/

# Usuario sem privilegios: um processo que so le dados nao precisa de root.
RUN useradd --create-home --uid 1000 vagas \
    && mkdir -p /app/data \
    && chown -R vagas:vagas /app
USER vagas

EXPOSE 8000

# DATABASE_URL e obrigatoria: sem ela a API falha no startup. O docker-compose
# a define apontando para o Postgres do compose.
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
