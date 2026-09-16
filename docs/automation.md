# Automação — GitHub Actions

Dois workflows em `.github/workflows/`. Os dois repetem os comandos da máquina
local; não existe um segundo caminho de execução.

| Workflow | Arquivo | Quando roda | Acesso ao banco |
|---|---|---|---|
| CI | `ci.yml` | push em `main` e `feature/**`, pull request | nenhum |
| Coleta de vagas | `collect.yml` | todo dia pelo cron (`schedule`) e pelo botão *Run workflow* (`workflow_dispatch`) | Secret `DATABASE_URL` |

## CI

Equivalente local:

```powershell
pip install -r requirements.txt
python -m pytest -q
```

- Roda em Python **3.11** (Dockerfile e `render.yaml`) e **3.13** (onde o scraper
  roda), com `fail-fast: false`.
- Não recebe Secret nem faz scraping. As fontes são testadas contra respostas reais
  capturadas, e `tests/conftest.py` apaga `DATABASE_URL` e `COLLECTION_INTERVAL_DAYS`
  e ignora `.env.local`/`.env`. Um PR vindo de fork também passa, porque o GitHub
  não entrega secrets a forks.
- Coleta real depende de portais instáveis, então **não** é teste obrigatório de PR.

## Coleta

### Frequência: cron diário + guarda de intervalo

O `cron` do GitHub Actions é estático: não dá para gerá-lo a partir de uma
variável a cada execução. Por isso a frequência fica dividida em dois papéis:

- **O cron só acorda o workflow**, todo dia às `09:00 UTC` (`0 9 * * *`).
- **A guarda decide.** A execução agendada roda `python main.py --respect-interval`,
  que consulta em `collection_runs` a última coleta completa bem-sucedida.
  - Se ainda não passaram `COLLECTION_INTERVAL_DAYS` dias, a execução é
    registrada como `skipped`, com motivo e data prevista, e termina com exit 0
    **sem acessar nenhum portal**.
  - Senão, coleta normalmente.

**O projeto coleta a cada 2 dias** (`COLLECTION_INTERVAL_DAYS=2`). Mudar X não
exige commit, cron novo nem mudança de lógica: basta alterar a Variable (passo 2).

#### Horário: sempre UTC

- `09:00 UTC` é `06:00` em Brasília (UTC-3; o Brasil não tem horário de verão
  desde 2019). O horário que aparece no GitHub e em `collection_runs` é UTC.
- **O GitHub não garante o horário.** Execuções agendadas costumam atrasar,
  principalmente perto do começo de cada hora, e em picos de carga podem ser
  descartadas. Uma execução perdida só adia a coleta para o dia seguinte.
- `schedule` só roda a versão do workflow que está na **branch padrão** (`main`).
- Em repositório público, o GitHub **desativa workflows agendados depois de 60
  dias sem atividade** no repositório. Para reativar: *Actions → Coleta de vagas →
  Enable workflow*.

#### Regra da guarda

- **Compara datas em UTC, não horas.** Com X = 2 e a última coleta completa em
  15/09 (em qualquer horário), a execução de 16/09 é pulada e a próxima coleta
  roda em 17/09. Assim o cron que acorda às 09:02 não pula o dia só porque a
  coleta anterior começou às 09:05.
- **Contam como "última coleta"** só as execuções que:
  - gravaram no banco;
  - terminaram com `success` ou `partial`;
  - tinham **escopo completo**: todas as fontes da coleta padrão, os termos
    padrão, pelo menos 5 páginas por termo e o filtro de senioridade ligado.
- **Não contam:**
  - `failed`, para a execução seguinte tentar de novo;
  - `skipped`;
  - coletas de amostra (`--sources gupy`, `--max-pages 1`), sejam manuais ou
    locais.
- Sem nenhuma coleta registrada, a guarda deixa coletar.

Regras em `scraper/execucao.py`; consulta e gravação em `persistence/execucoes.py`.

### Equivalente local

```powershell
# o que a execução agendada faz
$env:COLLECTION_INTERVAL_DAYS = "2"
python main.py --max-pages 5 --trigger schedule --respect-interval --resumo coleta/resumo.md

# disparo manual padrão: força a coleta
python main.py --max-pages 5 --trigger manual --resumo coleta/resumo.md

# disparo manual sem banco, com uma fonte
python main.py --max-pages 1 --trigger manual --sources gupy --no-db --csv --no-charts --resumo coleta/resumo.md
```

### Inputs do disparo manual

| Input | Padrão | Vira |
|---|---|---|
| `modo` | `banco` | `sem-banco` acrescenta `--no-db --csv --no-charts` |
| `fontes` | vazio (fontes padrão) | `--sources ...`; nomes separados por espaço, validados pelo `argparse` |
| `max_paginas` | `5` | `--max-pages N`; precisa ser inteiro positivo |
| `respeitar_intervalo` | `false` | `true` acrescenta `--respect-interval` |

A execução agendada não tem inputs: sempre grava no banco, com as fontes padrão, 5
páginas por termo e a guarda.

**Fontes padrão:** Gupy, Vagas.com.br, Trampos.co, LinkedIn, Quero Vagas Tech e
GeekHunter. A **ProgramaThor fica fora**: desde 15/09/2026 ela responde HTTP 403
para os servidores do GitHub Actions. A fonte continua no código e funciona da
máquina local com `--sources programathor`, e as vagas antigas dela continuam na
API. A lista fica em `scraper/sources/__init__.py` (`FORA_DA_COLETA_PADRAO`).

**Forçar uma coleta:** dispare manualmente com `respeitar_intervalo=false`, que é o
padrão. A coleta roda mesmo dentro do intervalo. Se tiver escopo completo e não
falhar, reinicia a contagem de X dias.

### 1. Preparar o banco

O workflow **não roda migrations**. A coleta não altera o schema, e o log do
Alembic mostra host e usuário do banco. Antes da primeira execução, e sempre que
entrar uma migration nova (a etapa 06 criou `collection_runs`), aplique as
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

### 2. Cadastrar o Secret e a Variable

**`DATABASE_URL` é Secret.** Cadastre só no repositório, nunca em arquivo
versionado:

- **Interface web:** *Settings → Secrets and variables → Actions → New repository
  secret*. Nome `DATABASE_URL`; cole a URL **pooled** da branch Neon `dados-main`,
  a branch de dados reais da `main` (veja `docs/neon-setup.md`).
- **GitHub CLI:** `gh secret set DATABASE_URL`, **sem** `--body`. O `gh` pede o
  valor interativamente, e a URL não fica no histórico do shell.

`gh secret list` confirma que o Secret existe, sem mostrar o valor.

**`COLLECTION_INTERVAL_DAYS` é Variable**, porque não é segredo:

- **Interface web:** *Settings → Secrets and variables → Actions → aba Variables →
  New repository variable*. Nome `COLLECTION_INTERVAL_DAYS`; valor inteiro positivo.
  O do projeto é `2`.
- **GitHub CLI:** `gh variable set COLLECTION_INTERVAL_DAYS --body 2`.
  `gh variable list` mostra o valor atual.

A variável é obrigatória para a execução agendada e não tem valor padrão no
código. Sem ela, ou com valor inválido (`0`, `2.5`, texto), a execução termina com
exit 2 antes de acessar banco e portais.

### 3. Disparar manualmente

- **Interface web:** *Actions → Coleta de vagas → Run workflow*. Escolha a branch e
  os inputs.
- **GitHub CLI:**

  ```powershell
  gh workflow run collect.yml --ref main -f modo=sem-banco -f fontes="gupy" -f max_paginas=1
  gh workflow run collect.yml --ref main -f respeitar_intervalo=true
  gh run watch
  ```

**Limitação:** o GitHub só mostra o botão e só aceita o disparo se o
`collect.yml` estiver na branch padrão (`main`). A partir daí, `--ref` escolhe a
branch cujo código roda.

**Primeira execução:** use `modo=sem-banco` com uma fonte. Portais de vaga
costumam bloquear IP de nuvem (ver [`api.md`, "Deploy"](api.md#deploy)). Esse modo mostra quais
fontes respondem ao runner do GitHub sem gravar nada no Neon.

### 4. Ler o resultado

O **resumo** do job (aba *Summary*) vem de `--resumo`. Ele mostra status,
gatilho, motivo e:

- em execução pulada: a data prevista da próxima coleta;
- em coleta: o funil, o **status de cada fonte**, o ranking e as contagens do
  banco.

Só entram contagens, nomes de fonte, status e tipos de erro.

#### Última e próxima coleta

Toda execução com banco e X conhecido informa, no terminal e logo abaixo do
status no resumo:

```
Última coleta: dia 15/09/2026 e próxima: dia 17/09/2026 (a cada 2 dias).
```

- **Última coleta** é a última coleta **completa** que não falhou. Se a execução
  atual for uma delas, é hoje.
- **Próxima** é a última + X dias. Se essa data já passou (a coleta de hoje
  falhou, ou não há coleta registrada), é amanhã, porque o cron acorda todo dia e
  tenta de novo. Sem coleta registrada, aparece "Última coleta: nenhuma
  registrada".
- **As datas são em UTC.** O cron roda às 09:00 UTC (06:00 em Brasília), então a
  data é a mesma do Brasil. Uma execução local depois das 21:00 em Brasília já
  cai no dia seguinte em UTC.
- É **previsão**, não horário garantido (veja "Horário: sempre UTC").
- A execução agendada sempre tem X. Uma execução forçada também informa as datas
  se `COLLECTION_INTERVAL_DAYS` estiver definida; no workflow, está.
- A mesma data da próxima coleta fica gravada em `collection_runs.next_run_on`.

#### Vagas repetidas e vagas encerradas

**A partir da segunda coleta, a mesma vaga nunca entra de novo.** Ela é
identificada por `(source, external_id)`: a coleta só atualiza quando a vaga foi
vista, e grava snapshot novo só se o conteúdo mudou.

**Uma vaga que some da listagem em duas coletas completas seguidas é considerada
preenchida e é encerrada:** `is_active = false` e `closed_at` com a data. Ela não
é apagada, porque o histórico fica. Contagens e gráficos que leem `jobs` usam só
`is_active = true`.

- **Só fontes confiáveis naquela coleta podem encerrar:**
  - coleta de escopo completo que não falhou;
  - status da fonte `ok`;
  - pelo menos uma vaga listada.

  Uma fonte `partial` ou `failed`, ou que voltou vazia sem erro (pode ser mudança
  no HTML do portal), não encerra nada.
- **"Vista"** é qualquer vaga que o portal ainda lista, mesmo que os filtros a
  descartem nesta coleta (por exemplo, o título virou "Pleno").
- **A primeira ausência só marca** `missing_since`. A segunda, em **outro dia
  (UTC)**, encerra. Duas coletas no mesmo dia (uma agendada e uma forçada) contam
  como uma. Com coleta a cada 2 dias, uma vaga preenchida sai em cerca de 4 dias.
- **Se a vaga reaparecer**, a ausência zera; se já estava encerrada, volta a
  ativa.
- **Por que duas ausências:** a coleta lê no máximo 5 páginas por termo, e uma
  vaga ainda aberta pode ficar fora delas numa coleta.

O resumo mostra quantas vagas foram encerradas e quantas sumiram pela primeira
vez. Os números por fonte ficam em `collection_runs.summary`.

**Hoje nenhum gráfico lê `jobs`.** Os PNGs do `--csv` usam só as vagas da coleta
atual, e a API lê a tabela legada `vagas`. O filtro por `is_active` passa a valer
no dashboard (etapa 07).

#### Status de cada fonte

| Status | Quando |
|---|---|
| `ok` | trouxe vagas sem falha e sem alerta de qualidade alto |
| `partial` | trouxe vagas, mas alguma requisição falhou (por exemplo, uma página bloqueada), um termo quebrou ou alguma vaga não foi gravada |
| `failed` | não trouxe vagas e alguma requisição ou termo falhou (portal bloqueado ou fora do ar), ou nenhuma vaga dela foi gravada |

"Requisição falha" é aquela em que `PoliteSession` desistiu: erro de rede, HTTP ≥
400 depois dos retries, ou resposta que deveria ser JSON e não é. As fontes só
param de paginar nesse caso, então é esse contador que impede um portal
bloqueado de aparecer como "0 vagas, tudo certo".

Uma fonte que quebra por inteiro (exceção fora do isolamento por termo) é
isolada: vira `failed` e as outras seguem gravando normalmente.

Uma fonte que volta com **0 vagas sem nenhuma falha**, ou com uma queda brusca,
gera um alerta de qualidade alto e vira `partial`. Regras, limites e ações estão em
[`docs/data-quality.md`](data-quality.md).

#### Status da execução e exit code

| Status | Quando | Exit | Job |
|---|---|---|---|
| `success` | todas as fontes `ok` | 0 | verde |
| `partial` | alguma fonte não ficou `ok`, mas houve vagas | 0 | verde; a fonte aparece destacada no resumo |
| `partial` | houve vaga não gravada no banco (regra da etapa 04) | 1 | vermelho |
| `partial` | alerta de qualidade de severidade alta (fonte zerada, queda brusca, valor fora do domínio, campo essencial vazio) | 1 | vermelho; a seção *Qualidade* do resumo diz qual |
| `failed` | todas as fontes falharam, ou nenhuma vaga foi encontrada | 1 | vermelho |
| `skipped` | a guarda pulou: intervalo ainda não cumprido | 0 | verde |
| — | erro de configuração: Secret ou Variable ausente/inválido, banco inacessível, schema atrasado | 2 | vermelho |

Se a própria linha de `collection_runs` não puder ser gravada, as vagas já
gravadas ficam, o resumo mostra o aviso e a execução sai com exit 1.

### 5. Auditoria

Toda execução com banco vira uma linha em `collection_runs`, inclusive as
puladas. Para ver as últimas:

```sql
SELECT started_at, triggered_by, status, full_scope, interval_days,
       reason, next_run_on, jobs_count, failures
FROM collection_runs
ORDER BY started_at DESC
LIMIT 10;
```

`next_run_on` é a próxima coleta prevista, a mesma data informada no resumo.
A coluna `summary` guarda, por fonte, status, requests, requests falhos, vagas
brutas, número de avisos e contagens da gravação, além da lista `qualidade` com os
alertas da execução. Nenhuma mensagem de erro entra ali. Estrutura em
`docs/data-model.md`; alertas em `docs/data-quality.md`.

### 6. Diagnóstico de falhas

Quando o job falha, ele sobe o artefato `coleta-diagnostico-<run_id>`, com
retenção de 7 dias:

- `coleta.sanitizado.log`: stdout/stderr da coleta, depois de
  `scripts/sanitizar_log.py`. Saem o valor do Secret e suas partes (senha,
  usuário, host), qualquer `esquema://usuario:senha@...`, qualquer URL PostgreSQL
  e hosts `*.neon.tech`.
- `resumo.md`: o mesmo resumo do job.

O log bruto **nunca** sobe. O GitHub mascara o valor exato dos secrets no log do
job, mas não em artefatos, e não mascara pedaços da URL, como o host.

Para ligar um job à linha do banco, o log e o resumo trazem o `GITHUB_RUN_ID` e o
`collection_runs.id` da execução, e `summary.github_run_id` guarda o primeiro.
Frescor dos dados, monitor externo e playbook de incidentes estão em
[`docs/observability.md`](observability.md).

### 7. Primeiro merge na `main`

Antes do merge, a `dados-main` precisa estar com `alembic upgrade head` e com o
seed importado, e a `DATABASE_URL` cadastrada no Render e no Secret. Depois do
merge, verifique nesta ordem:

1. **API:** o Render faz o deploy da `main`. `/health` responde `200`, e `/areas`
   e `/vagas?limit=1` respondem com dados.
2. **Portais contra o IP do GitHub, sem tocar no banco:**
   `gh workflow run collect.yml --ref main -f modo=sem-banco -f fontes="gupy" -f max_paginas=1`
3. **Coleta completa com banco**, forçada:
   `gh workflow run collect.yml --ref main`. O *Summary* mostra status, fontes e
   "Última coleta: dia … e próxima: dia …".
4. **Registro:** `collection_runs` na `dados-main` tem a execução. Conte só
   números e datas.
5. **Agendamento:** `gh workflow view collect.yml` mostra o workflow habilitado.
   A próxima execução é às 09:00 UTC, e a guarda pula até completar 2 dias.

Se algo der errado: `docs/rollback-merge.md`.

## Segurança

- `permissions: contents: read` nos dois workflows; checkout com
  `persist-credentials: false`.
- `DATABASE_URL` só entra no `env` dos passos *Coletar* e *Sanitizar log*.
  `COLLECTION_INTERVAL_DAYS` vem de `vars`, nunca de `secrets`.
- Os inputs chegam ao script por variáveis de ambiente, nunca interpolados no
  `run` (evita injeção de shell).
- A coleta roda sem `-v`: o log DEBUG pode incluir a mensagem do driver com o
  host.
- `concurrency: coleta` impede duas coletas simultâneas no mesmo banco, inclusive
  uma agendada e uma manual.
- `tests/test_workflows.py` verifica essas regras a cada CI, inclusive que o cron
  é diário e que a execução agendada passa `--respect-interval`.
