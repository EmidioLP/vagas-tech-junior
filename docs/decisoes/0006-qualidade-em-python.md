# ADR 0006 — Checagens de qualidade em Python, sem ferramenta dedicada

- **Status:** aceito
- **Data:** 16/09/2026 (decidido na etapa 11)

## Contexto

Um portal pode mudar o HTML ou a API e passar a devolver zero vagas **sem erro**.
Sem checagem, a coleta seria `success`, e o encerramento fecharia as vagas daquela
fonte. As regras necessárias são poucas e específicas do domínio: fonte zerada,
queda brusca contra o histórico, área/modalidade fora do vocabulário, campos
vazios acima do normal **por fonte** (o LinkedIn nunca traz descrição). Os dados
já passam por Python, e o histórico de volumes está em `collection_runs`.

## Decisão

- Regras em **`scraper/qualidade.py`**, funções puras sobre o resultado da
  coleta, rodando em `_aplicar_politica`: depois da gravação e **antes** do
  encerramento de ausentes.
- Alertas **altos** mudam a fonte de `ok` para `partial` (ela não encerra vagas) e
  forçam exit 1 (job vermelho). Os **baixos** só aparecem. Nenhum alerta corrige
  ou apaga dado.
- Limites são constantes no topo do módulo, calibrados com a coleta de 15/09/2026,
  com isenções por fonte. Um teste garante que essa coleta não gera alerta.
- Os alertas saem no resumo do job, em `collection_runs.summary` e no log.

Detalhes: [`../data-quality.md`](../data-quality.md).

## Consequências

- **Ganha:** nenhuma dependência nova; regras testadas como o resto do código;
  integração direta com o status e com o encerramento, que é justamente o que
  protege o histórico.
- **Custa:**
  - sem catálogo de expectativas, relatório navegável nem perfilamento automático:
    cada regra nova é código e teste;
  - limites recalibrados à mão, citando o dado que justifica o novo valor;
  - a regra de queda brusca só vale com pelo menos 3 coletas completas no
    histórico e mediana de pelo menos 30 vagas: fontes pequenas e começo de histórico ficam sem
    ela;
  - checa a coleta, não o banco inteiro. Problemas em dados antigos não são
    varridos.

## O que mudaria a decisão

- Muitas tabelas ou fontes, com regras genéricas repetidas (unicidade, not-null,
  faixas). Aí uma ferramenta declarativa (Great Expectations, testes do dbt,
  Soda) economiza código.
- Necessidade de relatórios de qualidade para outras pessoas, fora do job do
  Actions.
