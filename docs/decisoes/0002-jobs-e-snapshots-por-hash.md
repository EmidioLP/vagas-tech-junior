# ADR 0002 — `jobs` + snapshots gravados por hash

- **Status:** aceito
- **Data:** 16/09/2026 (decidido nas etapas 03 e 04; encerramento na 06)

## Contexto

A pergunta do projeto ("qual área contrata mais júnior") só faz sentido ao longo do
tempo, então cada coleta precisa acrescentar histórico sem duplicar vagas. A
mesma vaga é vista em várias coletas seguidas, quase sempre sem mudança.
Sobrescrever perderia o histórico; gravar uma linha por vaga por coleta encheria
o banco de cópias idênticas (cerca de 600 vagas a cada 2 dias). E a vaga que sai de
um portal precisa ser distinguida de uma falha de coleta.

## Decisão

- **`jobs`** guarda identidade e ciclo de vida: única por `(source, external_id)`,
  com `first_seen_at`, `last_seen_at`, `is_active`, `missing_since` e `closed_at`.
  Upsert idempotente pela constraint do banco, não por dedupe em memória.
- **`job_snapshots`** guarda o estado observado (título, empresa, descrição, área,
  modalidade, tecnologias…). Um snapshot novo **só é gravado quando o
  `content_hash` muda**: SHA-256 dos campos gravados, versionado em
  `persistence/assinatura.py` (`VERSAO = 1`).
- **Nada é apagado.** A FK dos snapshots é `RESTRICT`. Uma vaga só é encerrada
  depois de faltar em duas coletas confiáveis de dias UTC diferentes (escopo
  completo, fonte `ok` com pelo menos uma vaga listada).

Detalhes: [`../data-model.md`](../data-model.md).

## Consequências

- **Ganha:** rodar de novo é seguro; o banco cresce com as mudanças, não com as
  coletas; "estado atual" é uma consulta só (`persistence/foto_atual.py`),
  compartilhada por API e dashboard; uma fonte que falha não fecha vagas.
- **Custa:**
  - a série "vagas abertas por dia" não existe pronta: o dashboard a reconstrói
    em Python a partir de `first_seen_at`/`closed_at` e do snapshot vigente
    (`serie_historica`);
  - `closed_at` sai com atraso de pelo menos uma coleta, e uma vaga reaberta perde
    o registro do encerramento anterior
    ([limitação](../../dashboard/README.md#limitação-do-histórico));
  - mudar os campos do hash ou a normalização obriga a subir `VERSAO`, e a coleta
    seguinte grava um snapshot para **cada** vaga;
  - área e tecnologias entram no hash. Uma mudança em `scraper/rules/*.yml` gera
    snapshots novos para as vagas ainda vistas, mas não reclassifica o passado
    ([limitações](../limitacoes.md#mudança-de-regras-ao-longo-do-histórico)).

## O que mudaria a decisão

- Necessidade de reclassificar o histórico com regras novas. Isso exige guardar o
  dado bruto de cada coleta ([ADR 0004](0004-sem-medalhao-nem-dbt.md)).
- Consultas analíticas por dia frequentes ou pesadas demais para reconstruir em
  memória. Nesse caso, uma tabela diária materializada passaria a valer.
