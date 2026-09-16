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
- [ ] 09 — Camadas Bronze, Silver e Gold
- [ ] 10 — dbt para transformações
- [ ] 11 — Qualidade de dados
- [ ] 12 — API analítica
- [ ] 13 — Airflow para orquestração
- [ ] 14 — Observabilidade
- [ ] 15 — Deploy cloud
- [ ] 16 — Documentação de arquitetura e portfólio
- [ ] 17 — Auditoria final
