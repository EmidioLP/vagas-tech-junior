# ADR 0004 — Sem camadas Bronze/Silver/Gold nem dbt no volume atual

- **Status:** aceito
- **Data:** 16/09/2026 (roadmap revisado em 16/09/2026)

## Contexto

O roadmap original previa uma arquitetura medalhão (dado bruto → limpo →
agregado) e transformações em dbt. O volume é de cerca de 600 vagas de nível de
entrada por coleta, a cada 2 dias. Há dois consumidores (API e dashboard), e os
dois pedem o mesmo "estado atual" e as mesmas contagens. A transformação
(filtro, dedupe, classificação) já existe em Python, com testes contra respostas
reais dos portais, e as regras de negócio ficam em YAML.

## Decisão

- Não há camada bruta persistida nem camadas intermediárias. O pipeline grava
  direto o dado **normalizado e classificado** em `jobs`/`job_snapshots`, que já
  cumprem o papel de "silver com histórico" ([ADR 0002](0002-jobs-e-snapshots-por-hash.md)).
- O "gold" são consultas, não tabelas: `persistence/foto_atual.py` (estado atual),
  `api/crud.py` e `dashboard/consultas.py`, calculados na hora e com um teste que
  garante que API e dashboard devolvem os mesmos números.
- Nenhum dbt: não há SQL de transformação para versionar, e o schema já é versionado
  pelo Alembic.

## Consequências

- **Ganha:** um só lugar para cada regra (YAML + Python testado), nenhum job
  extra de transformação, nenhum dado agregado que envelhece fora de sincronia
  (`/areas` nunca lê `ranking_areas.csv`).
- **Custa:**
  - **não dá para reprocessar o passado.** O JSON/HTML bruto de cada portal é
    descartado depois da classificação. Vale para o bruto do portal; a **área**
    tem exceção, porque `job_snapshots` guarda `title` e `description`, que é
    tudo o que o classificador lê — `scripts/reclassificar_areas.py` refaz a
    classificação do histórico ([0008](0008-taxonomia-de-areas-expandida.md));
  - o LinkedIn não traz descrição, e o que foi descartado pelo portão de
    relevância ou pelo filtro de nível não fica em lugar nenhum para auditoria
    posterior. `collection_runs.summary` guarda só as vagas brutas por fonte e o
    total final; o funil completo sai no resumo do job e no log;
  - agregações por dia são refeitas em memória a cada consulta (com cache de 10
    minutos no dashboard).

## O que mudaria a decisão

- **Reclassificar o histórico** passar a ser requisito. O primeiro passo seria
  guardar o bruto por coleta (bronze, por exemplo em object storage), sem mexer
  no resto.
- **Mais consumidores com transformações diferentes** (outros recortes, modelos
  de ML, exportações periódicas). Aí transformações em SQL versionadas (dbt)
  passam a organizar melhor que consultas espalhadas.
- **Volume ordens de grandeza maior** (dezenas de milhares de vagas por coleta)
  ou consultas históricas lentas: agregados materializados passam a compensar o
  custo de mantê-los. Para a série histórica do dashboard, "lenta" já tem número
  medido em [0007](0007-serie-historica-em-python.md).
