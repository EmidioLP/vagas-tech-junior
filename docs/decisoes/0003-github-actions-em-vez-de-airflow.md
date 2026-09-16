# ADR 0003 — GitHub Actions em vez de Airflow

- **Status:** aceito
- **Data:** 16/09/2026 (decidido nas etapas 05 e 06; Airflow removido do roadmap
  na revisão de 16/09/2026)

## Contexto

A coleta é um único processo (`python main.py`) de alguns minutos, com cerca de
600 vagas a cada 2 dias. Ela precisa rodar agendada, fora da máquina local,
isolar falhas por portal, registrar cada execução e avisar quando falha. Não há
dependências entre tarefas além da ordem fixa do pipeline, nem vários pipelines, nem
equipe operando. O repositório já está no GitHub e o orçamento é zero.

## Decisão

- **`collect.yml`**: o cron acorda o workflow todo dia às 09:00 UTC, e a **guarda
  de intervalo** (`--respect-interval`, `scraper/execucao.py`) decide se coleta,
  lendo `collection_runs`. X vem de uma Repository Variable
  (`COLLECTION_INTERVAL_DAYS=2`). Também é possível disparar à mão.
- O que um orquestrador daria fica no próprio código: isolamento por fonte e por
  termo (`JobSource.fetch`, `collect`), status `success`/`partial`/`failed` com
  exit code, registro de toda execução (inclusive as puladas) em
  `collection_runs`, resumo no *Summary* do job e log sanitizado como artefato
  quando falha.
- Job vermelho + e-mail do GitHub são o alerta; `/health/dados` cobre o caso de o
  agendamento parar.

Detalhes: [`../automation.md`](../automation.md),
[`../observability.md`](../observability.md).

## Consequências

- **Ganha:** nenhuma infraestrutura para manter; o mesmo comando roda local e no
  Actions; o histórico de execuções fica no banco, consultável pela API e pelo
  dashboard; testes fixam as regras de segurança do workflow
  (`tests/test_workflows.py`).
- **Custa:**
  - o GitHub não garante o horário: execuções agendadas atrasam e podem ser
    descartadas, e uma perdida adia a coleta em um dia;
  - em repositório público, o agendamento é **desativado após 60 dias sem
    atividade**, e só um monitor externo percebe isso
    ([playbook](../observability.md#4-coleta-parada-ou-agendamento-desativado));
  - sem retry por tarefa nem backfill: uma coleta falha é refeita inteira no dia
    seguinte, e dias perdidos não podem ser recuperados (portal não guarda o passado);
  - IPs de nuvem são bloqueados por alguns portais (ProgramaThor), o que um
    orquestrador em nuvem não resolveria.

## O que mudaria a decisão

- Vários pipelines com dependências entre si (por exemplo, coleta → enriquecimento
  por vaga → agregações), ou necessidade de backfill e retry por etapa.
- Coleta que não caiba no limite de 60 minutos do job, ou frequência horária.
- Requisito de SLA de horário que o cron do GitHub não garante.
