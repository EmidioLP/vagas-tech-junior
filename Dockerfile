# Imagens do projeto para uso local (docs/docker.md). Um arquivo, tres alvos:
#
#   api        API somente leitura. E o ultimo estagio, entao `docker build .`
#              sem --target continua gerando a imagem da API.
#   dashboard  Streamlit somente leitura.
#   completa   Tudo do requirements.txt e o repositorio inteiro: serve a coleta
#              (`python main.py`) e aos testes, como o CI e o collect.yml fazem.
#
# O deploy publicado nao usa estas imagens: o Render instala requirements-api.txt
# direto, o dashboard roda no Streamlit Community Cloud e a coleta no GitHub
# Actions.

FROM python:3.11-slim AS base

# PYTHONUNBUFFERED: sem isso o log fica preso no buffer e o `docker compose logs`
# so mostra as mensagens quando o processo termina.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Usuario sem privilegios: nenhum dos processos precisa de root.
RUN useradd --create-home --uid 1000 vagas \
    && chown vagas:vagas /app


FROM base AS dashboard

# As dependencias entram antes do codigo para o cache de camadas do Docker
# sobreviver a cada alteracao em .py -- sem isso todo build reinstalaria tudo.
COPY requirements-dashboard.txt .
RUN pip install --no-cache-dir -r requirements-dashboard.txt

# `api/`, `persistence/` e `scraper/` entram porque o dashboard importa os
# modelos, a foto atual e a configuracao do banco de la. `.streamlit/` guarda as
# paletas por tema, lidas a partir do diretorio de trabalho.
COPY --chown=vagas:vagas api/ ./api/
COPY --chown=vagas:vagas persistence/ ./persistence/
COPY --chown=vagas:vagas scraper/ ./scraper/
COPY --chown=vagas:vagas dashboard/ ./dashboard/
COPY --chown=vagas:vagas .streamlit/ ./.streamlit/

USER vagas

EXPOSE 8501

# headless: nao tenta abrir navegador nem pergunta e-mail no primeiro boot.
CMD ["streamlit", "run", "dashboard/app.py", \
     "--server.address", "0.0.0.0", "--server.port", "8501", \
     "--server.headless", "true", "--browser.gatherUsageStats", "false"]


FROM base AS completa

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# O repositorio inteiro, menos o que o .dockerignore tira (segredos, dados
# gerados, node_modules). Os testes leem docs/, render.yaml e os workflows.
COPY --chown=vagas:vagas . .

# Destinos de `--csv` e `--resumo`; o compose monta as pastas da maquina aqui.
RUN mkdir -p /app/output /app/coleta \
    && chown vagas:vagas /app/output /app/coleta
USER vagas

CMD ["python", "-m", "pytest", "-q"]


FROM base AS api

COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# So o que a API precisa. `scraper/` entra porque a API le os YAMLs de regras
# (areas e tecnologias) de la. `persistence/` guarda a consulta da foto atual e a
# gravacao que a carga do seed usa. `alembic.ini`, `migrations/`, `scripts/` e
# `seed/` sao o que o servico `preparo` do compose roda antes da API subir.
COPY --chown=vagas:vagas alembic.ini ./
COPY --chown=vagas:vagas migrations/ ./migrations/
COPY --chown=vagas:vagas api/ ./api/
COPY --chown=vagas:vagas persistence/ ./persistence/
COPY --chown=vagas:vagas scraper/ ./scraper/
COPY --chown=vagas:vagas scripts/ ./scripts/
COPY --chown=vagas:vagas seed/ ./seed/

USER vagas

EXPOSE 8000

# DATABASE_URL e obrigatoria: sem ela a API falha no startup. O docker-compose
# a define apontando para o Postgres do compose.
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
