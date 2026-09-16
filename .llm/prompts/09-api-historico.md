# Prompt 09 — API sobre o modelo histórico

**Entrega:** a API pública serve as vagas que o pipeline grava (`jobs`/`job_snapshots`), com os mesmos números do dashboard e sem mudar o contrato das rotas existentes.

> **O problema real:** hoje API e dashboard respondem à mesma pergunta com dados diferentes. A API lê a tabela legada `vagas`, importada à mão de um CSV de 15/09/2026; o dashboard lê o que a coleta grava a cada 2 dias. Um produto que se contradiz não é confiável.

---

## O que mostrar antes

Mostre a contagem por área em `GET /areas` e no dashboard (Overview), com a data do dado de cada lado. Depois de implementar, as duas contagens devem coincidir para o mesmo banco.

## Contexto e objetivo

O modelo histórico já é a fonte da verdade e o dashboard já o consome. Troque a leitura da API para esse modelo, preservando rotas, filtros, paginação e respostas 404/422, sem ainda remover o fluxo legado.

## Analise exatamente isto

- `api/crud.py`, `api/routers/`, `api/schemas.py` e os modelos `Vaga`, `JobRecord`, `JobSnapshot` e `job_snapshot_tecnologias` em `api/models.py`.
- Em `dashboard/consultas.py`: `_vagas_atuais`, `_filtrar`, `distribuicao` e `indicadores_atuais`, que já definem a "foto atual" (vaga ativa + snapshot mais recente).
- Fixtures de `tests/api/conftest.py`, `tests/conftest.py` (`banco_historico`) e `tests/dashboard/cenario_historico.py`.

## Implemente somente isto

1. Extraia a consulta da "foto atual" para um único lugar usado pela API e pelo dashboard, sem que a camada de dados do dashboard passe a importar FastAPI, requests, bs4 ou yaml (há teste que verifica isso).
2. Reescreva `/vagas`, `/vagas/{id}`, `/areas` e `/tecnologias` sobre `jobs` + snapshot vigente, mantendo filtros (`area`, `tecnologia`, `modalidade`, `fonte`, `q`), `limit`/`offset` e os nomes dos campos da resposta.
3. Mapeie campo a campo o schema atual. Campo sem equivalente direto recebe o correspondente documentado (ex.: `created_at` → `first_seen_at`) ou sai com nota de mudança; nunca invente valor.
4. Por padrão, liste só vagas ativas. Se fizer sentido, adicione um parâmetro explícito para incluir as encerradas e documente-o no OpenAPI.
5. Faça `/health` deixar de depender da tabela `vagas`.
6. Atualize a seção de API do README, `docs/data-model.md` e `CLAUDE.md`: a API lê o modelo histórico e `vagas` passa a ser legada (ainda não removida).

## Arquivos/áreas esperados para revisão

`api/`, `dashboard/consultas.py` (só a extração), testes de API e dashboard, README e docs.

## Tecnologias envolvidas

FastAPI, Pydantic, SQLAlchemy, PostgreSQL/SQLite, pytest.

## Como verificar a entrega

1. A soma de `GET /areas` é igual a `vagas_ativas` do dashboard no mesmo banco.
2. `GET /vagas?area=X&modalidade=Y` retorna o mesmo total que a distribuição filtrada do dashboard.
3. Valores inválidos continuam retornando 422, e id inexistente, 404.
4. Uma vaga que deixou de citar uma tecnologia no snapshot mais recente não aparece em `?tecnologia=` dessa tecnologia.

## Armadilha importante

O `id` de `/vagas/{id}` muda de significado (`vagas.id` → `jobs.id`). Links antigos podem apontar para outra vaga ou dar 404. Registre isso como mudança de contrato no README e não tente manter os dois ids ao mesmo tempo.

## Restrições

- Não remova a tabela `vagas`, `scripts/import_csv.py`, `seed/vagas.csv` nem mude o Docker Compose nesta etapa.
- API continua somente leitura; nenhuma rota analítica nova.
- Filtros sempre como bind params; nada de SQL montado com texto do usuário.
- Não altere a ingestão nem o hash de snapshot.

## Testes

Use `banco_historico` e o cenário conhecido: equivalência API × consultas do dashboard, vaga encerrada fora do padrão, tecnologia do snapshot vigente, paginação e 422/404. Rode a suíte completa.

## Critérios de conclusão

- API e dashboard mostram os mesmos números para o mesmo banco.
- A regra da "foto atual" existe em um único lugar.

## Encerramento obrigatório

Mostre a comparação antes/depois e os testes. Depois do merge, confira `/areas` no Render contra o dashboard publicado. **PARE. Não remova o fluxo legado nem adicione checagens de qualidade.**
