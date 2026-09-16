# Status do roadmap — plataforma de dados

Etapas definidas em `.llm/prompts/`.

- **00 a 07a:** feitas na branch `feature/data-platform`, mesclada na `main` pelo
  PR #1 e depois apagada.
- **Da 08 em diante:** cada entrega é uma branch curta a partir da `main`,
  mesclada por pull request com o CI verde. A `main` é protegida, e o GitHub
  apaga a branch depois do merge.

- [x] 00 — Diagnóstico e linha de base
- [x] 01 — Neon e configuração segura
- [x] 02 — Alembic e base de migrations
- [x] 03 — Schema histórico: jobs e snapshots
- [x] 04 — Persistência direta e idempotência
- [x] 05 — GitHub Actions para CI e coleta manual
- [x] 06 — Intervalo configurável e resiliência por fonte
- [x] 07 — Dashboard Streamlit base
- [x] 07a — Preparação segura para o merge na main
- [x] 08 — Analytics e histórico no dashboard
- [x] 09 — API sobre o modelo histórico
- [x] 10 — Aposentar o fluxo legado
- [x] 11 — Qualidade da coleta
- [x] 12 — Frescor dos dados e monitoramento
- [x] 13 — Arquitetura e registro de decisões
- [x] 14 — Auditoria final ([`final-audit.md`](final-audit.md))

## Revisão do roadmap (16/09/2026)

As etapas 09 a 17 originais foram escritas para uma plataforma de dados genérica.
O objetivo do projeto é um produto de dados que funcione, então elas foram
reescritas a partir do que já existia:

- **Removidas:** camadas Bronze/Silver/Gold, dbt e Airflow. O volume (cerca de
  600 vagas por coleta, a cada 2 dias) não as justifica. `jobs`/`job_snapshots`
  já cumprem o papel de dado normalizado com histórico, e o GitHub Actions já
  agenda, isola fontes e registra execuções. O porquê vira ADR na etapa 13.
- **Removida:** deploy cloud, que já estava feito (API no Render, dashboard no
  Streamlit Community Cloud).
- **Novas:** 09 e 10. A API ainda lia a tabela legada `vagas`, importada de um
  CSV de 15/09/2026, e por isso divergia do dashboard.
- **Reduzidas:** qualidade de dados sem dbt (11), observabilidade limitada a
  frescor e monitoramento (12), documentação focada em arquitetura e decisões (13).

## Estrutura final da documentação (etapa 13)

- **Entrada:** `README.md`, com propósito, links publicados, achados datados,
  quickstart sem segredos e resumo das limitações.
- **Arquitetura:** [`architecture.md`](architecture.md), com o fluxo em Mermaid, os
  componentes, a estrutura do repositório e o mapa de todos os documentos.
- **Decisões:** [`decisoes/`](decisoes/README.md), ADRs 0001 a 0006. As remoções
  da revisão acima estão justificadas nos ADRs
  [0003](decisoes/0003-github-actions-em-vez-de-airflow.md) e
  [0004](decisoes/0004-sem-medalhao-nem-dbt.md).
- **Movidos do README, sem perda de conteúdo:** [`fontes.md`](fontes.md),
  [`classificacao.md`](classificacao.md), [`api.md`](api.md). O resumo das
  limitações ficou no README, e a versão completa, ampliada, em
  [`limitacoes.md`](limitacoes.md).
- **Inalterados:** os guias operacionais (`automation.md`, `data-model.md`,
  `data-quality.md`, `observability.md`, `deploy.md`, `neon-setup.md`,
  `migrations.md`, `rollback-merge.md`) e os registros datados (`baseline.md`,
  `resultados-2026-09-15.md`).

## Auditoria final (16/09/2026)

Resultado em [`final-audit.md`](final-audit.md). Confirmado com evidência: testes,
migrations, idempotência, coleta local das 6 fontes, API e dashboard (local e
publicados) com os mesmos números, frescor coerente com `collection_runs`, e
nenhum segredo versionado. Sem falha bloqueadora.

Ainda **não confirmado** (e por isso fora das caixas acima):

- `docker compose up --build`: Docker ausente na máquina da auditoria.
- Checagens de qualidade, correlação `github_run_id` e encerramento de vagas em
  produção: dependem das coletas agendadas de 17/09 e 19/09.

Mudanças maiores recomendadas (dependências de teste, Dependabot, actions por SHA)
ficam como etapas novas, não abertas aqui.
