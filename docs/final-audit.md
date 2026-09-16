# Auditoria final — 16/09/2026

Relatório da etapa 14. Objetivo: separar o que o projeto **comprova** com evidência
do que depende de ambiente ou de decisão humana. Nada foi "corrigido" para ficar
verde: falhas relevantes viram recomendação ou etapa nova.

## Escopo

| Item | Valor |
|---|---|
| Data | 16/09/2026, por volta das 18:50–19:20 UTC |
| Commit auditado | `476f766` (`main`, merge do PR #12), com o working tree limpo exceto o prompt da etapa 14 |
| Escopo | testes, migrations, coleta local, idempotência, API e dashboard locais, workflows, `render.yaml`, Compose, README e `docs/`, API e dashboard publicados (só leitura), `collection_runs` na branch Neon `dados-main` (só leitura), segurança do repositório |
| Fora do escopo | deploy, migrations no Neon, qualquer escrita em banco de produção, mudanças de código de produto |

Acesso ao banco de produção: a URL foi obtida pelo Neon CLI dentro do processo de
auditoria, nunca impressa nem gravada. As consultas usaram o papel
`dashboard_leitura`, o mesmo do dashboard publicado, pelo engine só de leitura de
`dashboard/config.py` (`transaction_read_only = on`, confirmado na sessão). A
versão do schema exigiu o papel dono, também em transação só de leitura, com um
único `SELECT` em `alembic_version`.

## Ambiente

| Ferramenta | Versão |
|---|---|
| SO | Windows 11 Pro (Git Bash e PowerShell) |
| Python | 3.13.9 (o CI testa 3.11 e 3.13) |
| fastapi / starlette / httpx | 0.141.1 / 1.3.1 / 0.28.1 |
| SQLAlchemy / psycopg / alembic | 2.0.43 / 3.3.4 / 1.18.4 |
| streamlit / pytest | 1.51.0 / 8.4.2 |
| gh / neon CLI / git | 2.96.0 / 4.18.0 / 2.53.0 |
| **Ausentes** | Docker, gitleaks, actionlint |

## Resultado consolidado

| Área | Resultado |
|---|---|
| Testes, migrations, idempotência | **Aprovado** |
| Coleta local (6 fontes) | **Aprovado** |
| API e dashboard locais | **Aprovado** |
| Docker Compose | **Não executado** (Docker ausente); evidência parcial aprovada |
| Consistência em produção (API × dashboard × `collection_runs`) | **Aprovado** |
| Links do README e dos docs | **Aprovado** |
| Segurança (segredos, workflows, papel do dashboard) | **Aprovado** |
| Falhas reais bloqueadoras | **Nenhuma** |
| Pendências | 3 verificações que só a próxima coleta agendada (17/09) permite; 6 recomendações |

## 1. Checklist de ponta a ponta

`$S` é um diretório temporário fora do repositório. `DATABASE_URL` e
`DATABASE_URL_UNPOOLED` foram removidas do ambiente de todos os comandos locais.

| # | Verificação | Comando | Resultado |
|---|---|---|---|
| 1 | Suíte completa | `python -m pytest -q` | **602 passed**, 0 skipped, 0 failed, 1 warning (depreciação do `httpx` no `starlette.testclient`, ver recomendação P2) |
| 2 | Migrations em SQL | `DATABASE_URL=postgresql://<fictícia>@localhost/offline alembic upgrade head --sql` | exit 0; 8 `CREATE TABLE`, 7 trocas de `alembic_version` (as 7 revisões) |
| 3 | Migrations aplicadas + `check` | `alembic.command.upgrade(cfg, "head")` e `command.check(cfg)` num SQLite em `$S` (o CLI só aceita URL PostgreSQL por projeto, `scraper/config.py:_validar_postgres`) | 7 revisões aplicadas, **"No new upgrade operations detected"**, head `85084f63871c` |
| 4 | Coleta local sem banco | `python main.py --no-db --csv --max-pages 1` | exit 0 em 526 s; **6/6 fontes `ok`, 0 requisições falhas**; 848 brutas → 766 nível de entrada → 593 sem duplicatas → **408** de tecnologia; 3 CSVs, relatório e 3 PNGs em `output/` |
| 5 | Idempotência | `scripts/carregar_seed.py --db $S/audit.db` duas vezes, contando linhas antes e depois | 1ª carga: 597 vagas e 597 snapshots criados. **2ª carga: 0 criadas, 0 snapshots novos, 0 falhas**, contagens idênticas (`jobs` 597, `job_snapshots` 597, `job_snapshot_tecnologias` 1734, `tecnologias` 114). Também coberto por `tests/api/test_persistencia.py` e `test_carregar_seed.py` (dentro do item 1) |
| 6 | Docker Compose | `docker compose up --build` | **Não executado: Docker não instalado.** Evidência parcial abaixo |
| 7 | Dashboard local | `DASHBOARD_DB=$S/audit.db streamlit run dashboard/app.py --server.headless true --server.port 8599`; `curl /_stcore/health` e `/`; renderização com `streamlit.testing.v1.AppTest` | health `ok`, HTTP 200; AppTest **sem exceções nem erros**, métricas: 597 vagas ativas, 475 empresas, 16,1% remoto, 7 fontes |
| 8 | API local | uvicorn com `api.app:app` sobre o mesmo SQLite (lançador em `$S` que troca `get_engine`) | `/health` 200 (597), `/areas` 200, `/vagas` 200 (total 597), `POST /vagas` **405**; `/health/dados` **503 `sem_coleta`**, esperado: o seed não grava `collection_runs` |
| 9 | YAML dos workflows | `yaml.safe_load` em `ci.yml`, `collect.yml`, `render.yaml`, `docker-compose.yml`; `gh workflow list`; `pytest tests/test_workflows.py tests/test_render_yaml.py tests/test_deploy_dashboard.py tests/test_sanitizar_log.py` | 4 arquivos válidos; os dois workflows `active`; **24 passed** |

**Evidência parcial do Compose (item 6).** Num venv novo só com
`requirements-api.txt` (as dependências da imagem, sem matplotlib nem streamlit), a
sequência do `command` do Compose rodou sobre SQLite: `alembic upgrade head` (7
revisões), `scripts/carregar_seed.py` (597 vagas, 0 falhas) e uvicorn servindo
`/health` 200, `/areas` 200 (10 áreas), `/tecnologias` 200 (114) e `/vagas` 200
(597). Não cobre: build da imagem, Postgres 16 do Compose, healthcheck
`pg_isready`, usuário `vagas` sem privilégios e portas.

Os processos locais (API, dashboard e a API do venv) foram encerrados, e as portas
8598/8599 ficaram livres ao fim.

## 2. Consistência em produção

Consultas feitas em 16/09/2026 por volta das 19:05 UTC.

| Verificação | API publicada | Banco (`dados-main`, funções do dashboard) | Resultado |
|---|---|---|---|
| Vagas ativas | `/health`: 603; soma de `/areas`: 603 | `consultas.vagas_ativas`: 603 | **Igual** |
| `/areas` × dashboard | 10 áreas | `consultas.distribuicao(…, "area")` | **Igual nas 10 áreas** |
| `/health/dados` × frescor | `em_dia`, última coleta 15/09 22:01Z `partial`, X=2, última execução 16/09 `skipped`, próxima 17/09 | `consultas.frescor`: mesmos 6 campos | **Igual** |
| Schema | — | `alembic_version` = `85084f63871c` | **No head** do repositório |
| Integridade | — | 603 `jobs`, 603 ativas, 0 encerradas, 0 com `missing_since`, 603 snapshots, **0 vagas sem snapshot** | Coerente |
| Dashboard publicado | — | `https://vagas-tech-junior.streamlit.app/` HTTP 200 (com cookie), `/_stcore/health` `ok` | **No ar** |
| Método não permitido | `DELETE /vagas/1` → **405** | — | Coerente com "somente leitura" |

**`collection_runs` (todas as linhas: são 2).**

| id | Início (UTC) | Gatilho | Status | Escopo completo | X | Próxima | Vagas | Falhas | Fontes | Alertas |
|---|---|---|---|---|---|---|---|---|---|---|
| 2 | 16/09 13:56 | schedule | `skipped` | sim | 2 | 17/09 | 0 | 0 | — (pulada pela guarda) | — |
| 1 | 15/09 22:01 | manual | `partial` | sim | — | 17/09 | 603 | 0 | 6 `ok`, `programathor` `failed` (0 brutas) | nenhum |

Cruzamento com o GitHub Actions: `collect.yml` tem 3 execuções, todas `success`
(15/09 21:59 manual, 15/09 22:01 manual e 16/09 13:55 schedule). A de 15/09 21:59
foi o disparo `modo=sem-banco` só com a Gupy (confirmado no log), que não grava
no banco, como descrito em `docs/automation.md` ("Primeira execução"). As outras duas correspondem às linhas 2
e 1. O status `partial` da linha 1 vem da ProgramaThor, que ainda estava na coleta
padrão e recebeu 403 do IP do runner. Isso motivou a exclusão dela no mesmo dia
(`docs/fontes.md`).

**Links.** Internos: 133 links com âncora em README, `CLAUDE.md`,
`dashboard/README.md` e `docs/`, **0 quebrados**. O script confere o arquivo e o
slug do título no estilo GitHub; foi testado com links quebrados de propósito.
Externos: **15/15 HTTP 200** (API publicada e exemplos, dashboard, repositório,
Render, Streamlit, endpoints públicos dos portais).

## 3. Segurança

| Verificação | Método | Resultado |
|---|---|---|
| Padrões de segredo no HEAD | varredura de todos os arquivos versionados: URL PostgreSQL com senha, `npg_…`, `*.neon.tech`, `ep-…`, tokens GitHub/`sk-`/`napi_`, atribuições `password=`/`token=`, chaves privadas | 30 ocorrências triadas uma a uma: **todas fictícias ou genéricas** (`senha-ficticia`/`outra-senha` com hosts `*.exemplo.test` nos testes; `<SENHA>@<host>-pooler.<região>.aws.neon.tech` em `docs/deploy.md`; `*.neon.tech` em texto e nas skills do Neon). Zero `npg_`, zero endpoint real, zero token |
| Mesmos padrões no histórico | `git log --all -p` (todas as refs) | Só as mesmas ocorrências fictícias, em 6 commits |
| **Valores reais** no histórico e nos logs | senhas, hosts e endpoints reais de 6 URLs (`.env.local` + `dados-main` pooled/direta, dois papéis) buscados como texto em `git log --all -p` e nos logs das 3 execuções do `collect.yml` | **Nenhum valor real encontrado** |
| Arquivos sensíveis versionados | `git log --all --diff-filter=A --name-only` | Só `.env.example`. `.env.local`, `.neon`, `.streamlit/secrets.toml`, `coleta/`, `data/`, `output/` confirmados por `git check-ignore`; `neon.ts` sem id nem segredo |
| Logs e artefatos do Actions | `gh run view --log` das 3 execuções; API de artefatos | Logs sem URL nem host (só as máscaras `***` do GitHub). **0 artefatos** (só são enviados em falha; retenção de 7 dias) |
| Permissões dos workflows | leitura do YAML + API do repositório | `permissions: contents: read` nos dois; `persist-credentials: false` nos dois checkouts; `DATABASE_URL` só nos passos *Coletar* e *Sanitizar log*; inputs por `env`, sem interpolação em `run`; sem `pull_request_target`; permissão padrão de workflow `read`, sem aprovação de PR por Actions |
| Repositório | API do GitHub | Público; **secret scanning e push protection ativos, 0 alertas**; `main` protegida (checks *Testes (Python 3.11)* e *(3.13)* obrigatórios e `strict`, PR obrigatório, force push bloqueado, regras valem para admins) |
| Papel `dashboard_leitura` | catálogo (`pg_roles`, `has_*_privilege`) na `dados-main` | `rolsuper`, `rolcreatedb`, `rolcreaterole`, `rolreplication`, `rolbypassrls` = false; sem papéis herdados; `rolconfig` = `default_transaction_read_only=on`; **só `SELECT`** em `jobs`, `job_snapshots`, `job_snapshot_tecnologias`, `tecnologias`, `collection_runs` (as 5 de `docs/deploy.md`); **nenhum privilégio** em `alembic_version`; sem `CREATE` no schema nem no banco; 0 sequências com `USAGE`/`UPDATE` |
| API | testes + produção | Só `GET`: `POST` local e `DELETE` publicado respondem 405; `/health/dados` expõe só estado e datas |

## 4. Itens aprovados

- Suíte completa verde (602) e as regras de configuração fixadas em teste
  (workflows, `render.yaml`, deploy do dashboard, sanitização de log).
- Migrations: SQL offline, upgrade do zero, `check` sem diferenças, e a produção no
  mesmo head.
- Persistência idempotente, comprovada com a mesma carga duas vezes.
- Coleta local com as 6 fontes padrão respondendo do IP local.
- API e dashboard sobem localmente, sem exceções, com os mesmos números.
- Em produção, API e dashboard dão os mesmos números por área e o mesmo frescor, e
  ambos batem com `collection_runs`.
- Nenhum segredo real versionado nem em log; papel do dashboard com privilégio
  mínimo; workflows com permissão mínima.

## 5. Falhas reais

**Nenhuma falha bloqueadora.** Defeitos encontrados, todos de texto e corrigidos
nesta etapa (seção 8):

| Severidade | Defeito | Evidência |
|---|---|---|
| Baixa | Comentários e doc citavam o "importador", removido na etapa 10 | `.env.example`, `requirements.txt`, `docs/migrations.md` |
| Baixa | `requirements.txt` dizia que a imagem da API não usa Alembic, mas `requirements-api.txt` inclui e o Compose roda `alembic upgrade head` no boot | `requirements-api.txt`, `docker-compose.yml` |

## 6. Limitações de ambiente e verificações pendentes

| Item | Por quê | Como fechar |
|---|---|---|
| `docker compose up --build` não executado | Docker ausente nesta máquina | Numa máquina com Docker: `docker compose up --build`; conferir `http://localhost:8000/health` (597 vagas) e `/areas`; `docker compose down -v` |
| Conteúdo do dashboard publicado não lido diretamente | O Streamlit renderiza por websocket; `curl` só vê o HTML base | A paridade foi verificada pelas mesmas funções do app contra o mesmo banco e pelo teste `tests/api/test_api_equivalencia_dashboard.py`. Conferência visual é manual |
| **Checagens de qualidade nunca rodaram em produção** | Foram mescladas em 16/09 às 14:28 UTC; as duas execuções registradas são anteriores | Ver a coleta agendada de **17/09** (seção *Qualidade* do resumo e `summary.qualidade`) |
| **Correlação `github_run_id` nunca gravada em produção** | Mesma razão (etapa 12, mesclada em 16/09 às 14:41 UTC). As 2 linhas não têm o campo | Conferir `summary.github_run_id` e o id no resumo da execução de 17/09 |
| **Encerramento de vagas nunca exercido** | Exige duas coletas completas confiáveis em dias diferentes; só existe uma | Só após a segunda coleta completa (17/09) aparece `missing_since`; `closed_at` só a partir da terceira |
| `alembic check` contra PostgreSQL | O CLI exige Postgres; rodou em SQLite. A produção foi conferida só pela revisão | `alembic check` com a URL direta de uma branch Neon temporária (`docs/migrations.md`) |
| Varredura de segredos sem ferramenta dedicada | gitleaks/trufflehog ausentes | Regras próprias + valores reais cobriram o risco principal; o secret scanning do GitHub está ativo |
| `actionlint` ausente | — | Parse YAML + aceitação pelo GitHub (`active`) + execuções verdes + `tests/test_workflows.py` |

## 7. Decisões humanas pendentes

- **Monitor externo** de `/health/dados` (manual e opcional em
  `docs/observability.md`): sem ele, um agendamento desativado pelo GitHub só é
  percebido por quem abrir a API ou o dashboard.
- **Conferir a coleta de 17/09** (os três primeiros itens pendentes da seção 6).
  Se vier alerta alto, seguir o playbook de `docs/observability.md`, sem afrouxar
  limites.
- **Pausa de 60 dias:** em repositório público, o GitHub desativa o agendamento
  sem atividade. Decidir quem reativa, ou aceitar o risco.

## 8. Correções feitas nesta etapa

| Arquivo | Antes | Depois | Evidência |
|---|---|---|---|
| `.env.example` | "Sem ela, a API e o importador falham na inicializacao." | "Sem ela, a API, a coleta (sem --no-db) e a carga do seed falham na inicializacao." | `scripts/import_csv.py` removido na etapa 10; `ConfiguracaoError` em API, pipeline e seed (`CLAUDE.md`, `docs/api.md`) |
| `requirements.txt` | "DATABASE_URL e obrigatoria para API e importador." / "A imagem da API nao usa." | "…para API, coleta e carga do seed." / "Tambem vai na imagem da API (requirements-api.txt): o docker-compose aplica as migrations no boot; o Render nao." | `requirements-api.txt` inclui `alembic`; `docker-compose.yml` roda `alembic upgrade head`; `render.yaml` não |
| `docs/migrations.md` | "A API (`init_db`) e o importador ainda criam tabelas… já tem o schema da baseline" | "A API (`init_db`) ainda cria as tabelas que faltam… já tem o schema atual dos modelos" | `api/database.py:init_db` usa `create_all` sobre os modelos atuais; `tests/api/test_migrations.py` roda `create_all` + `stamp` + `check` |

Também foram atualizados `docs/roadmap-status.md` (etapa 14) e `docs/architecture.md`
(mapa dos documentos). Nenhum código, teste, migration, limite de qualidade ou
regra foi alterado.

## 9. Recomendações priorizadas

| Prioridade | Recomendação | Por quê | Forma |
|---|---|---|---|
| **P1** | Verificar a coleta agendada de 17/09 (status por fonte, seção *Qualidade*, `github_run_id`, `next_run_on` = 19/09 e as primeiras `missing_since`) e a de 19/09 (primeiros `closed_at`) | Qualidade, correlação e encerramento só foram provados em teste, nunca com dado real | Operação (sem código) |
| **P1** | Rodar `docker compose up --build` numa máquina com Docker e anexar o resultado a este relatório | Único item do checklist sem execução real | Operação |
| **P2** | Preparar a troca de `httpx` por `httpx2` para o `TestClient` e fixar faixas de versão de `fastapi`/`starlette` | O único warning da suíte é a depreciação do `httpx` no `starlette.testclient` (starlette 1.3.1), que já sugere `httpx2`. Como `fastapi` não tem teto de versão, uma release futura do starlette pode quebrar os testes da API no CI sem nenhuma mudança no repositório | **Etapa nova** (mudança de dependência e de testes) |
| **P2** | Ativar Dependabot (atualizações de segurança) e fixar as actions por SHA | Dependabot desativado; `actions/*@v7` por tag | **Etapa nova** (config de repositório e workflows) |
| **P3** | Configurar o monitor externo sugerido em `docs/observability.md` | Único sinal independente do GitHub para o agendamento parado | Decisão humana, fora do repositório |
| **P3** | Instalar gitleaks/actionlint localmente ou no CI | Tornar a varredura de segredos e a validação de workflows reproduzíveis por ferramenta, não por script ad hoc | Etapa nova, opcional |
