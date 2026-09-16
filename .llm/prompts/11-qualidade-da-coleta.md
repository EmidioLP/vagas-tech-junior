# Prompt 11 — Qualidade da coleta

**Entrega:** cada coleta verifica se o resultado é plausível (fonte que zerou, queda brusca, valores fora do domínio, classificação degenerada) e deixa o resultado registrado e visível.

> **O incidente provável:** um portal muda o HTML, o parser deixa de achar cards, nenhuma requisição falha, e a fonte sai como `ok` com 0 vagas (`scraper/execucao.py:status_fonte`). O dashboard mostra um mercado encolhendo que não existe.

---

## O que mostrar antes

Monte, em teste, uma execução em que uma fonte retorna 0 vagas sem erro e mostre que hoje ela termina como `success`. Depois da etapa, a mesma execução deve gerar um alerta registrado.

## Contexto e objetivo

Unicidade e integridade já são garantidas pelo banco (`(source, external_id)`, FKs `RESTRICT`), e o código tem testes com respostas reais capturadas. Falta verificar o **dado** de cada execução. Faça isso em Python/SQL dentro do pipeline, proporcional ao volume do projeto, sem dbt nem Great Expectations.

## Analise exatamente isto

- `scraper/execucao.py` (status por fonte e da execução), `scraper/pipeline.py`, `persistence/execucoes.py` e `CollectionRun.summary`.
- Histórico real de `collection_runs` por fonte, para calibrar limites. Quero Vagas Tech e LinkedIn são grandes; Trampos.co e ProgramaThor são naturalmente pequenos.
- Campos que algumas fontes nunca informam (ex.: LinkedIn sem descrição, Vagas.com sem híbrido).

## Implemente somente isto

1. Módulo puro de checagens (ex.: `scraper/qualidade.py`) que recebe o resultado da execução e o histórico recente e devolve alertas com regra, fonte, severidade e valor observado.
2. Regras iniciais:
   - fonte padrão com 0 vagas brutas sem erro;
   - queda por fonte abaixo de um limite em relação à mediana das últimas execuções de escopo completo;
   - área fora de `areas.yml` e modalidade fora do domínio;
   - URL que não é http/https;
   - `published_date` no futuro;
   - fatia de "Outros/TI Geral" acima de um teto.
3. Regra de nulidade só por fonte, com limites documentados. Nunca `not null` global para campo opcional.
4. Grave os alertas em `collection_runs.summary`, sem mensagens de erro nem dados sensíveis, e inclua-os no `--resumo`.
5. Defina a consequência: severidade alta vira status `partial` (fonte `ok` com 0 vagas deixa de ser `ok`); severidade baixa só aparece no resumo. Documente regras, limites, severidade e ação em `docs/data-quality.md`.

## Arquivos/áreas esperados para revisão

`scraper/`, `persistence/execucoes.py`, testes, `docs/data-quality.md` e `docs/automation.md`.

## Tecnologias envolvidas

Python, SQLAlchemy, pytest.

## Como verificar a entrega

1. Fonte com 0 vagas brutas e sem erro gera alerta de severidade alta e a execução não sai como `success`.
2. Queda brusca em uma fonte grande gera alerta; a variação normal de uma fonte pequena não gera.
3. Área ou modalidade fora do domínio é detectada com fonte e contagem.
4. Os alertas aparecem no resumo do Actions e em `collection_runs.summary`.

## Armadilha importante

Limite apertado demais vira ruído, e alerta ignorado não serve para nada. Calibre com o histórico real, trate a primeira execução (sem histórico) sem falso positivo e não compare coletas de escopo parcial com as completas.

## Restrições

- Não adicione dbt, Great Expectations ou outro serviço.
- Checagens nunca apagam nem corrigem dados gravados; só sinalizam.
- Não altere o hash de snapshot nem as regras de classificação.
- Não mude a regra da guarda de intervalo sem documentar o efeito de `partial`.

## Testes

Para cada regra, um caso que dispara e um caso normal que não dispara, incluindo a primeira execução sem histórico. Teste a integração com o status da execução. Rode a suíte completa.

## Critérios de conclusão

- Uma fonte quebrada silenciosamente é detectada na mesma execução.
- Cada alerta tem regra, severidade e ação documentadas.

## Encerramento obrigatório

Mostre as regras, os limites calibrados e os testes. **PARE. Não implemente frescor dos dados, health check ou alertas externos.**
