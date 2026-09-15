"""Persistencia das vagas coletadas no historico (jobs + job_snapshots).

Fica fora de `scraper/`: as fontes e o pipeline nao escrevem SQL. O pipeline so
importa `persistence.repositorio` quando vai gravar, entao `--no-db` funciona
sem SQLAlchemy. `persistence.assinatura` e puro e nao depende de banco.
"""
