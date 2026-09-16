# Registro de decisões (ADRs)

Decisões de arquitetura que definem a forma do projeto. Cada uma é curta e segue o
mesmo formato:

- **Status** e **data** do registro;
- **Contexto:** o problema e as restrições reais (volume, custo, plataforma);
- **Decisão:** o que foi escolhido;
- **Consequências:** o que ganha e o que custa;
- **O que mudaria a decisão:** o sinal concreto para revisitar.

As decisões foram tomadas ao longo das etapas de `.llm/prompts/` e registradas
aqui em 16/09/2026, na etapa 13. Uma decisão nova ou revertida vira um ADR novo; o
antigo recebe `Status: substituído por NNNN` em vez de ser apagado.

| ADR | Decisão |
|---|---|
| [0001](0001-neon-com-branches.md) | Neon PostgreSQL com branches separando desenvolvimento e dados reais |
| [0002](0002-jobs-e-snapshots-por-hash.md) | `jobs` para identidade + `job_snapshots` gravados só quando o hash muda |
| [0003](0003-github-actions-em-vez-de-airflow.md) | GitHub Actions para agendar a coleta, em vez de Airflow |
| [0004](0004-sem-medalhao-nem-dbt.md) | Sem camadas Bronze/Silver/Gold nem dbt no volume atual |
| [0005](0005-render-e-streamlit-community-cloud.md) | API no Render e dashboard no Streamlit Community Cloud |
| [0006](0006-qualidade-em-python.md) | Checagens de qualidade em Python, sem ferramenta dedicada |

Visão geral do fluxo: [`../architecture.md`](../architecture.md).
