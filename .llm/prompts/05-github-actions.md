# Prompt 05 — GitHub Actions para CI e coleta manual

**Entrega:** testes rodam em PR/push e a coleta pode ser disparada manualmente no GitHub Actions, usando `DATABASE_URL` somente como Secret.

> **Por que agora:** automação só entra depois da idempotência. Um botão manual primeiro permite observar o pipeline em CI antes de deixá-lo rodar sozinho.

---

## O que mostrar antes

Mostre os comandos locais reais de teste e coleta. O workflow deve repeti-los, não inventar um segundo caminho de execução.

## Contexto e objetivo

O pipeline manual já persiste no Neon de forma idempotente. Agora adicione automação no GitHub Actions de modo seguro e observável, começando por execução manual e CI; o agendamento configurável virá depois.

## Analise exatamente isto

- Comandos reais de lint/teste/coleta; dependências e versões Python.
- Configuração de segredos e documentação Neon.
- Workflows existentes e limitações dos scrapers em CI.

## Implemente somente isto

1. Crie/atualize workflow de CI para rodar testes em push/pull request, sem acesso a `DATABASE_URL` de produção.
2. Crie `.github/workflows/collect.yml` com `workflow_dispatch`, recebendo opcionalmente seleção de fonte/modo seguro se isso for útil ao projeto.
3. Na coleta manual, leia `DATABASE_URL` exclusivamente de GitHub Secrets e execute o comando oficial do pipeline; nunca imprima a URL.
4. Faça upload de logs/sumário não sensíveis como artefatos quando houver falha.
5. Documente como cadastrar Secret e disparar workflow em `docs/automation.md`.

## Arquivos/áreas esperados para revisão

`.github/workflows/`, scripts/CLI de coleta, requirements, `.gitignore`, documentação.

## Tecnologias envolvidas

GitHub Actions, GitHub Secrets, Python, pytest, Neon PostgreSQL.

## Como verificar a entrega

1. Um PR executa testes sem secret de produção.
2. `workflow_dispatch` exibe um resumo de coleta sem imprimir URL ou senha.
3. Um erro de coleta deixa artefato/log sanitizado para diagnóstico.

## Armadilha importante

Não use scraping de rede instável como teste obrigatório de PR. Teste código com fixtures; a coleta real fica no workflow manual/agendado.

## Restrições

- Sem `schedule` nesta etapa.
- Não commitar segredos nem emitir variáveis sensíveis em logs.
- Não executar scraping de teste na CI de PR se depender de rede/fontes instáveis.

## Testes

Valide YAML/sintaxe, execute localmente os comandos equivalentes quando possível e confirme que testes unitários não dependem de Secret. Revise permissões mínimas do workflow.

## Critérios de conclusão

- PR/push executa testes.
- Coleta é disparável manualmente e usa Secret com segurança.
- Falhas têm logs/sumário acessíveis sem vazar dados.

## Encerramento obrigatório

Liste workflows e validações. **PARE. Não implemente agendamento X dias, dashboard ou outras fases.**
