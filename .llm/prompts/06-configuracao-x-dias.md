# Prompt 06 — Intervalo configurável e resiliência por fonte

**Entrega:** `COLLECTION_INTERVAL_DAYS=X` controla a frequência efetiva; o workflow pode acordar diariamente, mas a coleta só roda quando deve. Falha de uma fonte não apaga sucesso das outras.

> **Por que não cron dinâmico:** GitHub Actions não cria um cron diferente a partir de variável em cada execução. O cron acorda o pipeline; a regra persistida decide executar ou pular.

---

## O que mostrar antes

Mostre o workflow manual e a última execução registrada. A prova desta etapa é um “skip” auditável, não apenas um cron escrito no YAML.

## Contexto e objetivo

Há coleta manual via Actions. Agora torne a periodicidade explicitamente configurável e assegure que uma fonte indisponível não invalide toda a execução. O objetivo é uma atualização a cada X dias, com comportamento transparente.

## Analise exatamente isto

- Workflow `collect.yml`, comando do pipeline e módulo de configuração.
- Como as fontes reportam erro e como o resumo de execução é construído.
- Limitações do cron GitHub Actions e fuso horário UTC.

## Implemente somente isto

1. Adote `COLLECTION_INTERVAL_DAYS` validado (inteiro positivo) como configuração documentada.
2. Implemente uma guarda persistida: antes de coletar, consulte a última execução bem-sucedida e pule de forma explícita se X dias ainda não passaram. Não tente gerar cron dinâmico, pois cron do GitHub é estático.
3. Defina um cron diário simples no workflow; ele invoca a guarda. Preserve `workflow_dispatch` para forçar execução manual de modo documentado.
4. Isole erros por fonte, continue com as demais e retorne status/sumário por fonte; falhe a execução apenas segundo política clara (por exemplo, todas as fontes falharam).
5. Registre execução e resultado mínimo em estrutura já adequada ao projeto ou tabela de controle com migration, sem antecipar Bronze.

## Arquivos/áreas esperados para revisão

Configuração, pipeline, fontes, migration/modelos de controle se necessários, workflow e `docs/automation.md`.

## Tecnologias envolvidas

Python, GitHub Actions cron, PostgreSQL/Neon, logging.

## Como verificar a entrega

1. Com última execução dentro de X dias, a execução agendada é marcada como skip com motivo e data prevista.
2. Ao passar X dias, coleta normalmente.
3. Uma fonte falha e as demais ainda persistem; todas falhando produz status claro.
4. Disparo manual forçado está documentado.

## Armadilha importante

Cron do GitHub é UTC. Documente o horário exibido e não prometa uma precisão de scheduler que a plataforma não oferece.

## Restrições

- Não adicione Airflow.
- Não esconda falhas: fonte falha deve aparecer no resumo.
- Cron é UTC; explique isso na documentação.

## Testes

Teste validação de X, decisão executar/pular, falha isolada de fonte, todas as fontes falhando e execução forçada. Rode a suíte inteira.

## Critérios de conclusão

- Alterar X não exige mudança de lógica nem cron novo.
- Atualizações repetidas antes do intervalo são puladas de modo auditável.
- Falhas parciais preservam resultados das fontes saudáveis.

## Encerramento obrigatório

Mostre os cenários testados. **PARE. Não inicie Streamlit, analytics, Bronze ou dbt.**
