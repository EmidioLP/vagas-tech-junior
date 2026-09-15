# Prompt 00 — Diagnóstico e linha de base

**Entrega:** a branch `feature/data-platform` está ativa, o estado atual do projeto foi registrado e a suíte de testes tem um resultado conhecido. Nenhuma feature nova é criada.

> **O momento “agora entendi”.** Antes de mudar banco, pipeline ou dashboard, precisamos conseguir responder: “o que já funciona hoje e como provamos que continuou funcionando amanhã?”

---

## O que mostrar antes

Mostre a árvore do repositório, a branch atual, `git status` e o comando de testes. O contraste desejado é simples: antes desta etapa não há um retrato confiável do ponto de partida; depois dela existe documentação e uma branch protegendo a evolução.

## Contexto e objetivo

O repositório `vagas-tech-junior` já possui scrapers de múltiplas fontes, pipeline, classificação, deduplicação, extração de skills, exportação CSV, API FastAPI, SQLAlchemy, Docker e uma suíte de testes. O objetivo desta etapa é **entender e registrar o estado atual sem alterar a arquitetura funcional**. Precisamos de uma linha de base confiável antes de introduzir Neon, migrations ou histórico.

## Analise exatamente isto

- A árvore do repositório, README, dependências e comandos de execução/teste.
- `scraper/` (fontes, `models.py`, `pipeline.py`, `dedupe.py`, classificação, exportação).
- API, modelos SQLAlchemy, scripts de importação e Docker Compose, se existirem.
- Testes atuais e eventuais pontos de acoplamento CSV → banco/API.
- Configurações existentes, `.env.example`, workflows CI e segredos expostos acidentalmente.

## Implemente somente isto

1. Verifique se a árvore de trabalho está limpa ou identifique alterações preexistentes. Sem apagar nem alterar trabalho alheio, crie e mude para a branch `feature/data-platform` a partir do estado estável atual. Se ela já existir, confirme que está nela e não recrie a branch.
2. Crie `docs/baseline.md` descrevendo: arquitetura atual, fluxo de dados, fontes, comandos verificados, contagem/resultado de testes, dependências relevantes, riscos e pontos que serão afetados nas próximas etapas.
3. Crie ou atualize `.env.example` apenas com nomes de variáveis e valores fictícios seguros, se ele não existir ou estiver incompleto.
4. Se não existir, crie um `docs/roadmap-status.md` com as 18 etapas deste plano como checklist; marque apenas esta etapa ao concluí-la.
5. Não refatore código de produção nesta etapa.

## Arquivos/áreas esperados para revisão

`README.md`, `requirements*.txt`/`pyproject.toml`, `scraper/`, `api/`, `scripts/`, `tests/`, `docker-compose.yml`, `.github/`, arquivos de ambiente e configuração.

## Tecnologias envolvidas

Python, pytest, FastAPI, SQLAlchemy, PostgreSQL e Docker apenas para inspeção/documentação.

## Como verificar a entrega

1. `git branch --show-current` retorna `feature/data-platform`.
2. `docs/baseline.md` descreve fluxo, fontes, comandos e resultado real dos testes.
3. `.env.example` não contém valores secretos.
4. A suíte de testes foi executada e o resultado está documentado.

## Se der errado

| Sintoma | Causa provável | Ação nesta etapa |
| --- | --- | --- |
| A árvore já está alterada | Trabalho anterior ainda não foi isolado | Documente os arquivos; não descarte nada nem misture mudanças sem confirmar a origem. |
| Testes falham | Falha preexistente ou ambiente incompleto | Registre comando, erro e impacto; não faça uma correção ampla ainda. |

## Restrições

- Não criar banco Neon, migrations, tabelas, dashboard, dbt ou Airflow.
- Não remover CSV, endpoints, testes ou comportamento existente.
- Não colocar credenciais, URLs reais com senha ou tokens em arquivos versionados.
- Não fazer merge, push forçado, rebase destrutivo ou modificar branch principal.

## Testes

Execute a suíte de testes existente e registre o comando e resultado no baseline. Caso haja falhas preexistentes, não as corrija de forma ampla: isole-as e documente-as.

## Critérios de conclusão

- `docs/baseline.md` permite a outra pessoa entender o estado atual e os pontos de integração.
- O resultado real dos testes está registrado.
- A branch `feature/data-platform` está ativa e é a única branch usada pelas etapas subsequentes.
- Nenhuma alteração funcional foi feita.

## Encerramento obrigatório

Mostre a branch ativa, os arquivos criados/alterados e o resultado dos testes. **PARE agora. Não implemente Neon, Alembic, schema, persistência nem qualquer etapa posterior. Aguarde o próximo prompt.**
