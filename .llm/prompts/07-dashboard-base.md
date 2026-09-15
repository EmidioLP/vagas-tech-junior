# Prompt 07 — Dashboard Streamlit base

**Entrega:** um dashboard Streamlit read-only sobe localmente e mostra que os dados existem, quando foram atualizados e quantas vagas ativas há.

> **O ponto visual:** antes, o banco é invisível para quem visita o projeto; depois, existe uma porta de entrada simples e honesta, mesmo sem gráficos sofisticados.

---

## O que mostrar antes

Mostre uma consulta que comprova dados no banco e, depois, a mesma informação na interface. O dashboard não coleta nem transforma dados.

## Contexto e objetivo

Dados históricos já chegam ao Neon. Crie uma interface pública mínima em Streamlit, somente de leitura, sem tentar entregar todos os gráficos analíticos agora.

## Analise exatamente isto

- Schema `jobs`/`job_snapshots`, consultas seguras já existentes na API e estilo do repositório.
- Configuração de ambiente e dependências de deploy.

## Implemente somente isto

1. Crie `dashboard/` com `app.py`, módulo de configuração e camada de consultas parametrizadas/read-only.
2. Mostre cabeçalho, data/hora da última coleta bem-sucedida, total de vagas ativas e aviso de dados indisponíveis.
3. Crie navegação/estrutura para Overview, Tecnologias, Histórico e Vagas, mas deixe páginas futuras com estado explícito de “em construção”; não invente analytics.
4. Use cache com TTL apropriado e tratamento de erro que não revele URL/segredos.
5. Documente execução local em `dashboard/README.md`.

## Arquivos/áreas esperados para revisão

Schema, API/queries existentes, requirements, configuração, novo `dashboard/`.

## Tecnologias envolvidas

Streamlit, SQLAlchemy/driver PostgreSQL, Neon.

## Como verificar a entrega

1. `streamlit run` inicia sem segredo no código.
2. A tela mostra última coleta, total ativo e estado vazio/erro amigável quando não há dados.
3. Acesso ao banco passa por uma camada única de queries e cache com TTL.

## Armadilha importante

Não transformar o dashboard em segundo pipeline: ele somente lê contratos estáveis do banco/API.

## Restrições

- Dashboard é read-only; não colete dados nem faça migrations.
- Não implemente gráficos históricos nem deploy nesta etapa.
- Segredos apenas em ambiente.

## Testes

Teste funções de consulta com banco/fakes isolados e faça smoke test de importação do app. Rode pytest.

## Critérios de conclusão

- App sobe localmente com configuração segura e mostra o estado básico dos dados.
- Estrutura suporta evolução sem duplicar acesso ao banco.

## Encerramento obrigatório

Mostre como executar e os testes. **PARE. Não implemente analytics, deploy, dbt ou Airflow.**
