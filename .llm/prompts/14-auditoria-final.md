# Prompt 14 — Auditoria final

**Entrega:** um relatório com evidências de que o que o projeto promete é verificável (testes, segurança, consistência entre API, dashboard e docs) e com as pendências reais visíveis.

> **O objetivo não é deixar tudo verde a qualquer custo.** É descobrir o que se sustenta com evidência e deixar claro o que depende de ambiente ou de decisão humana.

---

## O que mostrar antes

Mostre `git status`, `docs/roadmap-status.md` e a lista de comandos de validação que serão executados. A auditoria começa pelo estado, não por correções.

## Contexto e objetivo

As etapas do roadmap foram concluídas. Audite qualidade, segurança e coerência. Corrija apenas defeitos pequenos e comprovados; qualquer mudança maior vira uma etapa nova.

## Analise exatamente isto

- Git status/diff, testes, migrations, workflows, `render.yaml`, Compose, README e `docs/`.
- A API e o dashboard publicados, só em leitura e sem credenciais.
- As últimas linhas de `collection_runs` (status, alertas de qualidade, frescor).

## Implemente somente isto

1. Checklist de ponta a ponta:
   - `pytest` completo;
   - `alembic upgrade head --sql` e `alembic check`;
   - `python main.py --no-db --csv --max-pages 1` em ambiente local;
   - idempotência da persistência em SQLite temporário;
   - `docker compose up` com a API respondendo;
   - dashboard subindo localmente;
   - YAML dos workflows válido.
2. Consistência em produção: `/areas` da API × dashboard; `/health/dados` × última coleta registrada; links do README funcionando.
3. Segurança: segredos e URLs de banco versionados (inclusive no histórico do git), arquivos `.env*`, logs e artefatos do Actions, permissões dos workflows, privilégios do papel `dashboard_leitura`.
4. Corrija só erros pequenos de doc/config/teste e registre cada correção.
5. Produza `docs/final-audit.md` com data, escopo, comandos, resultados, itens aprovados, falhas reais, limitações de ambiente e recomendações priorizadas. Atualize `docs/roadmap-status.md` marcando só o que foi confirmado.

## Arquivos/áreas esperados para revisão

Repositório inteiro, com foco em configuração, CI, docs e testes.

## Tecnologias envolvidas

pytest, Alembic, FastAPI, Streamlit, GitHub Actions, Docker, PostgreSQL/Neon.

## Como verificar a entrega

1. `docs/final-audit.md` traz data, comandos, resultados, bloqueadores e recomendações.
2. A busca por segredos não encontra arquivo sensível versionado.
3. Os resultados separam aprovados, falhas reais e limitações de ambiente (ex.: portal que bloqueia IP local).

## Armadilha importante

Não "corrija" a auditoria apagando migrations, pulando testes, afrouxando limites de qualidade ou removendo regras. Falha relevante é registrada e vira etapa própria.

## Restrições

- Não reescreva arquitetura nem introduza tecnologia nova.
- Não faça deploy, não aplique migrations no Neon e não escreva no banco de produção.
- Não apague dados ou migrations para "limpar" o ambiente.
- Nenhum segredo, URL de banco ou host aparece no relatório.

## Testes

Execute tudo que for aplicável e registre comando e resultado; diferencie bloqueador de limitação ambiental.

## Critérios de conclusão

- Auditoria reproduzível e honesta, sem segredos expostos.
- Estado final e próximos passos estão claros.

## Encerramento obrigatório

Entregue o relatório e o resultado consolidado. **PARE. Não faça nenhuma implementação posterior sem novo pedido explícito.**
