# Prompt 04 — Persistência direta e idempotência

**Entrega:** `scraper → PostgreSQL` funciona diretamente; uma reexecução idêntica não infla `jobs` nem `job_snapshots`; CSV permanece apenas como exportação opcional.

> **O ponto de entrevista:** idempotência significa que rodar o pipeline duas vezes produz o mesmo estado final. Sem isso, automação só cria duplicação mais rápido.

---

## O que mostrar antes

Mostre o fluxo atual até CSV e os novos modelos. A mudança deve introduzir uma camada de persistência, não espalhar SQL dentro de cada fonte.

## Contexto e objetivo

O schema histórico existe. Agora conecte o pipeline atual ao PostgreSQL, tornando o banco a fonte de verdade e mantendo CSV apenas como exportação opcional. A operação deve ser idempotente: reexecutar a mesma coleta não pode criar duplicatas.

## Analise exatamente isto

- Fluxo `sources → pipeline → classifier/seniority/skills/dedupe → export`.
- Contratos de `Job`, deduplicação e scripts CSV legados.
- Schema `jobs` e `job_snapshots` criado na etapa anterior.

## Implemente somente isto

1. Crie uma camada/repositório de persistência isolada do scraper, com transações explícitas.
2. Faça upsert de `jobs` por `(source, external_id)`, atualizando `last_seen_at` e atividade sem apagar identidade.
3. Grave snapshot somente se o conteúdo observável mudou ou se a política documentada exigir uma observação nova; defina e documente uma assinatura/hash determinística dos campos relevantes. A mesma entrada, na mesma coleta, deve gerar no máximo um snapshot.
4. Faça o pipeline chamar a persistência após processamento. Preserve exportação CSV como saída opcional, não como pré-requisito da API/banco.
5. Produza resumo de execução com criados, atualizados, snapshots criados/ignorados e falhas.

## Arquivos/áreas esperados para revisão

`scraper/pipeline.py`, modelos, dedupe, exportação, scripts de importação, configuração, testes de integração.

## Tecnologias envolvidas

Python, SQLAlchemy, PostgreSQL, pytest.

## Como verificar a entrega

1. Primeira execução com fixture conhecida: cria uma vaga e seu snapshot.
2. Segunda execução idêntica: não cria duplicatas e atualiza apenas o necessário.
3. Execução com alteração observável: cria novo snapshot preservando o anterior.
4. Falha no meio de uma transação não deixa uma vaga parcialmente gravada.

## Armadilha importante

Não use a deduplicação em memória como substituto de constraint/transação no banco. Ela reduz ruído de uma coleta; integridade persistente precisa estar no banco e na camada de gravação.

## Restrições

- Não modifique a lógica de classificação/dedupe sem um teste que justifique.
- Não remova compatibilidade CSV de forma abrupta; marque o fluxo legado como exportação/depreciação se necessário.
- Uma falha de uma fonte não deve corromper gravações já confirmadas.

## Testes

Use banco de teste para validar: primeira ingestão; repetição idêntica; alteração que gera snapshot; mesma vaga com fontes/IDs distintos; rollback em erro. Execute a suíte completa.

## Critérios de conclusão

- Pipeline grava diretamente no banco e é idempotente.
- `jobs` não duplica e snapshots preservam mudanças.
- CSV não é a fonte de verdade.

## Encerramento obrigatório

Mostre o fluxo e contagens de um teste de integração. **PARE. Não crie GitHub Actions, cron ou dashboard.**
