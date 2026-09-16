# Prompt 08 — Analytics e histórico no dashboard

**Entrega:** o dashboard mostra KPIs, filtros e tendências temporais, distinguindo claramente vagas únicas de snapshots observados.

> **O diferencial:** “quantas vagas existem?” é fotografia. “como vagas de Data evoluíram nas últimas coletas?” só é possível porque o projeto preservou histórico.

---

## O que mostrar antes

Mostre uma vaga com mais de um snapshot e uma consulta agregada. Depois prove que o gráfico usa a semântica declarada, não contagens ambíguas.

## Contexto e objetivo

O dashboard base está pronto. Agora entregue indicadores úteis baseados em snapshots, evidenciando evolução do mercado sem alterar a ingestão.

## Analise exatamente isto

- Definições de ativo, coleta, área, modalidade e skills no modelo atual.
- Páginas e camada de consultas do dashboard.

## Implemente somente isto

1. Overview: KPIs de vagas ativas, empresas, percentual remoto e fontes, com definições visíveis.
2. Filtros parametrizados por período, fonte, área e modalidade.
3. Gráficos: distribuição por área/modalidade/fonte; série temporal de vagas/snapshots por data de coleta; top tecnologias apenas se as skills forem confiáveis.
4. Página Vagas com tabela paginada, link seguro e último avistamento; página Histórico com tendências e legenda metodológica.
5. Trate períodos sem dados e diferenças entre “vagas únicas” e “snapshots”.

## Arquivos/áreas esperados para revisão

`dashboard/`, modelos e consultas analíticas; não refatore scraper.

## Tecnologias envolvidas

Streamlit, SQL/PostgreSQL, biblioteca de gráficos já coerente com dependências.

## Como verificar a entrega

1. Cada filtro altera consulta e resultado de forma previsível.
2. Métricas explicam se contam `jobs` únicos ou `snapshots`.
3. Período sem dados exibe estado vazio útil, não gráfico enganoso.

## Armadilha importante

Não chame qualquer linha de “vaga coletada”: explicite a diferença entre vaga ativa, vaga única e observação/snapshot.

## Restrições

- Consultas parametrizadas; não interpolar filtros em SQL.
- Não adicionar Bronze/dbt nem publicar cloud nesta etapa.

## Testes

Teste agregações com dados conhecidos: filtros, zero dados, unicidade versus snapshots e série temporal. Faça smoke test do dashboard.

## Critérios de conclusão

- Usuário distingue claramente fotografia atual de histórico.
- Indicadores e gráficos respondem aos filtros com dados corretos.

## Encerramento obrigatório

Apresente métricas, definições e testes. **PARE. Não implemente Bronze/Silver/Gold, dbt, API nova ou deploy.**
