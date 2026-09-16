# ADR 0001 — Neon PostgreSQL com branches

- **Status:** aceito
- **Data:** 16/09/2026 (decidido na etapa 01)

## Contexto

A coleta roda no GitHub Actions, a API no Render e o dashboard no Streamlit
Community Cloud: três ambientes efêmeros que precisam do **mesmo** banco
persistente. O orçamento é zero. Antes, o projeto usava SQLite local e um CSV
importado, o que não serve para um processo agendado na nuvem. Também era preciso
testar mudanças de schema sem arriscar o histórico real.

## Decisão

- PostgreSQL gerenciado no **Neon**, plano gratuito, configurado por uma única
  `DATABASE_URL` (`scraper/config.py:obter_database_url`), sem banco padrão.
- **Branches Neon** separam os usos: `production` é o ponto de partida e nada é
  aplicado nela; `feature-data-platform` serve ao desenvolvimento local; `dados-main`
  guarda os dados reais, usados pela `main`, pelo Actions, pelo Render e pelo dashboard.
  Branches descartáveis, com expiração, servem para testar migrations e para backup antes de
  mudanças destrutivas.
- Schema versionado com **Alembic**. Na `dados-main`, as migrations são aplicadas
  **à mão**, com a URL direta, antes do merge que as traz. Nem o deploy nem a
  coleta migram.

Detalhes: [`../neon-setup.md`](../neon-setup.md), [`../migrations.md`](../migrations.md).

## Consequências

- **Ganha:** um banco para todos os consumidores; branch de teste com dados reais
  a custo zero; o `dashboard_leitura` separa leitura de escrita
  ([`../deploy.md`](../deploy.md)).
- **Custa:**
  - um passo manual e fácil de esquecer: se a migration não for aplicada antes do
    merge, a coleta e a API param com "schema desatualizado";
  - compute limitado no plano gratuito. O banco dorme sem uso e a primeira
    consulta demora; um monitor frequente o manteria acordado e estouraria a cota.
    Por isso o monitor externo sugerido checa a cada 1 hora
    ([`../observability.md`](../observability.md#por-que-não-checar-a-cada-5-minutos));
  - dependência de um fornecedor. Os testes não dependem dele (SQLite pelas
    mesmas migrations), e o Docker Compose sobe um Postgres local.

## O que mudaria a decisão

- Volume ou frequência que ultrapassem a cota gratuita de compute ou de armazenamento.
- Necessidade de migrar automaticamente no deploy, com mais pessoas mexendo no
  schema. Aí um passo de migration no pipeline de deploy compensaria o risco.
