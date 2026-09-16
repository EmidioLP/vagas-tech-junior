# Prompt 10 — Aposentar o fluxo legado

**Entrega:** nenhum consumidor depende mais de `vagas`/`vaga_tecnologia`, do `import_csv.py` ou do import de CSV no boot; o Docker Compose sobe a API com dados no modelo histórico.

> **Por que é uma etapa própria:** dois caminhos para o mesmo dado geram divergência silenciosa. Remover só é seguro depois que a troca de leitura (etapa 09) foi confirmada em produção.

---

## O que mostrar antes

Liste tudo que ainda toca o fluxo legado (código, testes, Compose, Dockerfile, docs, CLAUDE.md) e prove que a API no Render já responde a partir de `jobs`.

## Contexto e objetivo

A API já lê o modelo histórico. Remova o caminho legado de ponta a ponta, preservando uma forma reprodutível de subir a API localmente com dados, sem rede.

## Analise exatamente isto

- `scripts/import_csv.py`, `seed/vagas.csv`, `docker-compose.yml`, `Dockerfile`, `render.yaml` e seus testes.
- Modelos `Vaga`, `vaga_tecnologia` e `Tecnologia`. `tecnologias` também é referenciada por `job_snapshot_tecnologias` e **não pode sair**.
- `semear_tecnologias` em `persistence/repositorio.py` e as referências em `docs/neon-setup.md`, `docs/rollback-merge.md` e README.

## Implemente somente isto

1. Decida e documente como o Compose ganha dados sem rede. Recomendado: converter `seed/vagas.csv` em uma carga do modelo histórico (via `persistence.persistir_vagas`, com `collected_at` fixo da coleta do seed) executada depois de `alembic upgrade head`.
2. Remova `Vaga`, `vaga_tecnologia`, o importador legado e os testes que só existiam para eles; mantenha `tecnologias` e sua semeadura.
3. Crie a migration Alembic que remove as tabelas legadas, com `downgrade` que as recria vazias.
4. Atualize Compose, Dockerfile, README, `CLAUDE.md`, `docs/neon-setup.md` e `docs/data-model.md`, removendo instruções de reimportar o seed.
5. Escreva em `docs/neon-setup.md` o passo manual para aplicar a migration na `dados-main`: criar branch Neon de backup antes, aplicar, verificar a API.

## Arquivos/áreas esperados para revisão

`api/models.py`, `alembic/versions/`, `scripts/`, `seed/`, Docker, testes e docs.

## Tecnologias envolvidas

Alembic, SQLAlchemy, Docker Compose, Neon (branch de backup).

## Como verificar a entrega

1. `grep` por `Vaga\b`, `vaga_tecnologia` e `import_csv` não encontra uso fora de migrations antigas e histórico de docs.
2. `docker compose up --build` sobe a API com vagas em `/vagas` sem acesso à internet.
3. `alembic upgrade head` e `alembic downgrade -1` funcionam em SQLite temporário; `alembic check` passa.

## Armadilha importante

A migration que apaga tabela é irreversível para os dados. Ela não pode rodar na `dados-main` como efeito colateral do merge: o workflow de coleta não roda migrations, e isso deve continuar assim. A aplicação em produção é um passo manual, com backup, pedido explicitamente ao operador.

## Restrições

- Não aplique migration no Neon nem apague dados reais sem autorização explícita.
- Não remova `tecnologias`, `jobs`, `job_snapshots` ou `collection_runs`.
- Não edite migrations antigas; crie uma nova.

## Testes

Teste a carga do seed no modelo histórico (idempotente ao rodar duas vezes), a migration de ida e volta e o `alembic check`. Rode a suíte completa.

## Critérios de conclusão

- Existe um único caminho de dados: coleta → modelo histórico → API/dashboard.
- Subir o projeto localmente continua simples e sem rede.

## Encerramento obrigatório

Mostre o que foi removido, a migration e o passo manual de produção. **PARE. Não aplique a migration no Neon sem pedido explícito e não avance para qualidade de dados.**
