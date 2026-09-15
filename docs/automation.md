# Automação — GitHub Actions

Dois workflows em `.github/workflows/`. Os dois repetem os comandos da máquina
local; não existe um segundo caminho de execução.

| Workflow | Arquivo | Quando roda | Acesso ao banco |
|---|---|---|---|
| CI | `ci.yml` | push em `main` e `feature/**`, pull request | nenhum |
| Coleta manual | `collect.yml` | só pelo botão *Run workflow* (`workflow_dispatch`) | Secret `DATABASE_URL` |

Não há agendamento nesta etapa: intervalo configurável é a etapa 06.

## CI

Equivalente local:

```powershell
pip install -r requirements.txt
python -m pytest -q
```

- Roda em Python **3.11** (Dockerfile e `render.yaml`) e **3.13** (onde o scraper
  roda), com `fail-fast: false`.
- Não recebe Secret nem faz scraping. As fontes são testadas contra respostas reais
  capturadas, e `tests/conftest.py` apaga `DATABASE_URL` e ignora `.env.local`/`.env`.
  Um PR vindo de fork também passa, porque o GitHub não entrega secrets a forks.
- Coleta real depende de portais instáveis, então **não** é teste obrigatório de PR.

## Coleta manual

Equivalente local do que o passo *Coletar* executa:

```powershell
# modo banco (padrão)
python main.py --max-pages 5 --resumo coleta/resumo.md

# modo sem-banco, com uma fonte
python main.py --max-pages 1 --sources gupy --no-db --csv --no-charts --resumo coleta/resumo.md
```

### Inputs

| Input | Padrão | Vira |
|---|---|---|
| `modo` | `banco` | `sem-banco` acrescenta `--no-db --csv --no-charts` |
| `fontes` | vazio (todas) | `--sources ...`; nomes separados por espaço, validados pelo `argparse` |
| `max_paginas` | `5` | `--max-pages N`; precisa ser inteiro positivo |

### 1. Preparar o banco

O workflow **não roda migrations**. A coleta não altera o schema, e o log do
Alembic mostra host e usuário do banco. Antes da primeira execução, aplique as
migrations localmente no banco que será usado:

```powershell
neon checkout <branch-de-coleta>          # grava a URL no .env.local
neon env pull --service postgres
alembic upgrade head
```

Se o schema estiver atrasado, a coleta termina **antes de acessar os portais**,
com exit 2 e a mensagem "O banco não está com o schema atual".

Use uma branch Neon própria para a automação, nunca a `production`
(`docs/neon-setup.md`).

### 2. Cadastrar o Secret

Cadastre só no repositório, nunca em arquivo versionado:

- **Interface web:** *Settings → Secrets and variables → Actions → New repository
  secret*. Nome `DATABASE_URL`; cole a URL **pooled** da branch Neon.
- **GitHub CLI:** `gh secret set DATABASE_URL`, **sem** `--body`. O `gh` pede o
  valor interativamente, e a URL não fica no histórico do shell.

`gh secret list` confirma que o Secret existe, sem mostrar o valor.

### 3. Disparar

- **Interface web:** *Actions → Coleta manual → Run workflow*. Escolha a branch e
  os inputs.
- **GitHub CLI:**

  ```powershell
  gh workflow run collect.yml --ref main -f modo=sem-banco -f fontes="gupy" -f max_paginas=1
  gh run watch
  ```

**Limitação:** o GitHub só mostra o botão e só aceita o disparo se o
`collect.yml` estiver na branch padrão (`main`). A partir daí, `--ref` escolhe a
branch cujo código roda.

**Primeira execução:** use `modo=sem-banco` com uma fonte. Portais de vaga
costumam bloquear IP de nuvem (ver README, "Deploy"). Esse modo mostra quais
fontes respondem ao runner do GitHub sem gravar nada no Neon. Uma fonte bloqueada
aparece como avisos no resumo e não derruba as outras.

### 4. Ler o resultado

O **resumo** do job (aba *Summary*) vem de `--resumo` e mostra:

- status e exit code;
- funil (brutas → senioridade → duplicadas → tecnologia);
- requests, vagas e avisos por fonte;
- ranking de áreas;
- contagens do banco (vagas criadas/atualizadas, snapshots criados/ignorados,
  falhas).

Só entram contagens, nomes de fonte e tipos de erro.

| Exit | Significado | Job |
|---|---|---|
| 0 | Coleta gravada (ou exportada em `sem-banco`) | sucesso |
| 1 | Nenhuma vaga encontrada, ou falhas ao gravar vagas | falha |
| 2 | Erro de configuração: Secret ausente/inválido, banco inacessível, schema atrasado | falha |

### 5. Diagnóstico de falhas

Quando o job falha, ele sobe o artefato `coleta-diagnostico-<run_id>`, com
retenção de 7 dias:

- `coleta.sanitizado.log`: stdout/stderr da coleta, depois de
  `scripts/sanitizar_log.py`. Saem o valor do Secret e suas partes (senha,
  usuário, host), qualquer `esquema://usuario:senha@...`, qualquer URL PostgreSQL
  e hosts `*.neon.tech`.
- `resumo.md`: o mesmo resumo do job.

O log bruto **nunca** sobe. O GitHub mascara o valor exato dos secrets no log do
job, mas não em artefatos, e não mascara pedaços da URL, como o host.

## Segurança

- `permissions: contents: read` nos dois workflows; checkout com
  `persist-credentials: false`.
- `DATABASE_URL` só entra no `env` dos passos *Coletar* e *Sanitizar log*.
- Os inputs chegam ao script por variáveis de ambiente, nunca interpolados no
  `run` (evita injeção de shell).
- A coleta roda sem `-v`: o log DEBUG pode incluir a mensagem do driver com o
  host.
- `concurrency: coleta` impede duas coletas simultâneas no mesmo banco.
- `tests/test_workflows.py` verifica essas regras a cada CI.
