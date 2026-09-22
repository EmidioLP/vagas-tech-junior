# Observabilidade

O que responder quando algo parece errado: **quando** a coleta rodou, **o que**
coletou, **o que falhou**, se a **qualidade** passou e se os dados estão
**vencidos**. Tudo sai do que o projeto já registra: nenhuma ferramenta paga nem
stack de métricas.

## Sinais e onde olhar

| Sinal | Onde | O que diz |
|---|---|---|
| Job vermelho e e-mail do GitHub | Actions → *Coleta de vagas* | coleta falhou (exit 1): todas as fontes falharam, vaga não gravada ou alerta de qualidade alto |
| Resumo da execução | *Summary* do job | status, fontes, funil, seção *Qualidade*, banco, agenda e ids de correlação |
| `collection_runs` | banco (`dados-main`) | uma linha por execução, inclusive as puladas: status, motivo, contagens por fonte, alertas |
| `GET /health` | API (Render) | **liveness**: processo e banco respondem. Sempre 200 se estiverem de pé |
| `GET /health/dados` | API (Render) | **frescor**: 200 em dia, **503** se os dados venceram, a coleta parou ou não há coleta |
| Aviso amarelo no Overview | dashboard | a mesma regra de frescor, para quem só abre o dashboard |
| Artefato `coleta-diagnostico-<run_id>` | job com falha | log sanitizado e resumo, por 7 dias |

`/health` e `/health/dados` são separados de propósito. O Render usa `/health` para
decidir se a API está saudável. Se ele respondesse erro por dado velho, o Render
reiniciaria uma API que funciona, e o problema continuaria sendo a coleta.

## Frescor (`persistence/frescor.py`)

O intervalo X entre coletas vem de `collection_runs.interval_days`, gravado pelas
execuções agendadas. Assim API e dashboard não dependem de `COLLECTION_INTERVAL_DAYS`,
que só existe no GitHub Actions. Datas são comparadas por dia UTC, como na guarda de
intervalo.

| Estado | Quando | `/health/dados` | Aviso no dashboard |
|---|---|---|---|
| `em_dia` | última coleta completa com até 2 × X dias e alguma execução nos últimos 2 dias | 200 | não |
| `sem_intervalo` | há coleta, mas nenhuma execução agendada gravou X | 200 | não |
| `vencido` | última coleta completa (`success`/`partial`) com mais de 2 × X dias | **503** | sim |
| `coleta_parada` | dado ainda dentro do limite, mas nenhuma execução registrada há mais de 2 dias | **503** | sim |
| `sem_coleta` | nenhuma coleta completa registrada | **503** | tela de banco vazio |
| `indisponivel` | banco não respondeu (só o tipo do erro aparece) | **503** | "Dados indisponíveis" |

Com X = 1 (a coleta diária adotada em 22/09/2026), o dado vence a partir de
**3 dias** sem coleta completa, o que continua tolerando uma coleta perdida — a
tolerância é de uma coleta, e a janela de relógio acompanha X.
`coleta_parada` continua querendo dizer a mesma coisa — o cron acorda todo dia e
registra até as execuções puladas, então dois dias sem nenhuma linha em
`collection_runs` significam agendamento parado.

**Com X = 1 os dois limiares se encontram no 3º dia, e `vencido` vem primeiro na
cadeia.** Com X = 2, um agendamento parado acendia `coleta_parada` no 3º dia e só
virava `vencido` no 5º — o aviso de "cron morreu" chegava antes do dado estragar.
Agora, no cenário de cron parado, o estado que aparece é `vencido`. Nada é perdido
em alerta (os dois respondem **503** e os dois estão em `ESTADOS_COM_PROBLEMA`), só
em rótulo: para separar "cron parado" de "coleta falhando", leia
`dias_desde_ultima_execucao` e `status_ultima_execucao`, que vêm na mesma resposta.
Se houver execuções recentes, o problema é a coleta; se não houver, é o
agendamento. Foi uma escolha consciente: ver
[ADR 0009](decisoes/0009-coleta-diaria.md).

A resposta nunca traz URL, host, usuário nem mensagem do driver:

```json
{
  "estado": "em_dia",
  "saudavel": true,
  "ultima_coleta": "2026-09-21T15:30:58Z",
  "status_ultima_coleta": "partial",
  "dias_desde_ultima_coleta": 1,
  "intervalo_dias": 1,
  "limite_dias": 2,
  "ultima_execucao": "2026-09-22T09:02:40Z",
  "status_ultima_execucao": "success",
  "dias_desde_ultima_execucao": 0,
  "proxima_coleta": "2026-09-23"
}
```

## Correlação de uma execução

Três ids ligam o que aconteceu:

- **`GITHUB_RUN_ID`**: aparece no log (`Execução iniciada (GitHub run <id>)`), no
  resumo (`GitHub run`), em `collection_runs.summary.github_run_id` e no nome do
  artefato de diagnóstico;
- **`collection_runs.id`**: aparece no log (`Execução registrada:
  collection_runs.id=<n>`) e no resumo (`Registro`);
- execuções locais não têm run do GitHub: o log diz `(local)`.

```sql
SELECT id, started_at, status, reason, summary->>'github_run_id' AS github_run
FROM collection_runs
ORDER BY started_at DESC
LIMIT 10;
```

## Metas modestas

- **Dados:** a última coleta completa com no máximo 2 × X dias (`/health/dados`
  200).
- **Agendamento:** nenhum período de mais de 2 dias sem uma linha em
  `collection_runs`.
- **Qualidade:** nenhum alerta alto sem investigação até a próxima coleta.
- **API:** responde em até ~60s. O plano free do Render hiberna após 15 minutos e
  leva ~50s para acordar.
- **Dashboard (Histórico):** a série do período completo em até 5s contra a
  `dados-main` (`DASHBOARD_DB=<url> python scripts/medir_serie_historica.py`; em
  21/09/2026 eram 0,6s, quase todo ida e volta até o Neon). Acima disso, o
  agrupamento sai do Python e vai para o banco
  ([ADR 0007](decisoes/0007-serie-historica-em-python.md)).

São metas de um projeto de portfólio sem plantão: servem para saber o que olhar,
não para cobrar disponibilidade.

## Retenção

| Registro | Por quanto tempo |
|---|---|
| `collection_runs` | sem expiração (algumas linhas por dia) |
| Artefato de diagnóstico | 7 dias (`collect.yml`) |
| Logs e resumos do Actions | padrão do GitHub para o repositório |
| Snapshots e vagas | sem expiração; nada é apagado |

## Playbook

### 1. Todas as fontes falharam

- **Sintoma:** job vermelho, status `failed`, motivo "todas as fontes falharam".
- **Diagnóstico:** tabela *Por fonte* do resumo (requests falhos) e o log
  sanitizado do artefato. Costuma ser rede do runner ou bloqueio dos portais ao IP
  do GitHub.
- **Ação:** disparar de novo à mão (`gh workflow run collect.yml`). A execução
  `failed` não conta para a guarda, então o cron do dia seguinte também tenta. Se
  persistir, testar localmente com `python main.py --no-db --csv --sources <fonte>`.

### 2. Alerta de qualidade alto

- **Sintoma:** job vermelho, status `partial`, seção *Qualidade* com linha em
  negrito.
- **Diagnóstico e ação:** tabela de regras em
  [`docs/data-quality.md`](data-quality.md). A fonte afetada não encerra vagas
  enquanto o alerta persistir.

### 3. Dados vencidos

- **Sintoma:** `/health/dados` responde 503 com `vencido`, e o dashboard mostra
  aviso.
- **Diagnóstico:** `collection_runs` recentes. Há execuções, mas `failed` ou fora do
  escopo completo? Então é o caso 1 ou coletas manuais parciais. **Com X = 1,
  `vencido` também cobre o caso 4**: se `dias_desde_ultima_execucao` na resposta for
  maior que 2, não há execução nenhuma e o problema é o agendamento, não a coleta.
- **Ação:** corrigir a causa e disparar uma coleta completa manual.

### 4. Coleta parada ou agendamento desativado

- **Sintoma:** `/health/dados` com `coleta_parada`, e nenhuma execução nova no
  Actions.
- **Diagnóstico:**

  ```powershell
  gh workflow view collect.yml
  gh run list --workflow collect.yml --limit 5
  ```

  O GitHub **desativa agendamentos** de repositórios públicos sem atividade por 60
  dias e avisa por e-mail. Também pode ser o workflow desabilitado à mão
  (`docs/rollback-merge.md`) ou falta de minutos do Actions.
- **Ação:** `gh workflow enable collect.yml` e uma coleta manual
  (`gh workflow run collect.yml`) para voltar a ter dado em dia.

### 5. API fora do ar

- **Sintoma:** `/health` não responde ou dá erro.
- **Diagnóstico:** *Render → vagas-tech-junior-api → Logs/Events*. Variável
  `DATABASE_URL` removida? Deploy novo quebrado?
- **Ação:** rollback no Render ou revert do merge ([`docs/rollback-merge.md`](rollback-merge.md)).

## Monitor externo (manual, opcional)

Um monitor que **não depende do GitHub** é o que percebe o caso 4: se o agendamento
parar, nenhum workflow vai avisar. A sugestão é um monitor HTTP gratuito, como o
UptimeRobot, checando **a cada 1 hora** (ou até 6 horas):

1. Criar a conta e um monitor do tipo HTTP(s) para
   `https://vagas-tech-junior-api.onrender.com/health/dados`.
2. Intervalo de **60 minutos**. O dado só vence em dias (2 × X), então checar mais
   vezes não antecipa nenhum alerta útil.
3. Alertar quando o status não for 2xx, com e-mail como canal.
4. Timeout no máximo que o plano permitir e alerta só depois de **2 falhas
   seguidas**. Com o intervalo longo, o Render estará sempre hibernando na checagem
   e pode levar ~50s para acordar; uma falha isolada costuma ser só isso.

### Por que não checar a cada 5 minutos

Cada checagem de `/health/dados` consulta o banco, e o Neon só suspende o compute
depois de ~5 minutos sem nenhuma consulta. Um monitor a cada 5 minutos manteria o
banco acordado 24 horas por dia: com a menor instância (0,25 CU), cerca de 180
CU-horas por mês, acima do limite do plano free (confira o valor atual no painel do
Neon). `/health` também consulta o banco, então trocar de endpoint não resolve.

A cada 1 hora, o banco acorda no máximo 24 vezes por dia e volta a dormir em
minutos: da ordem de 2 a 3 CU-horas por mês. O mesmo vale para o Render, que também
volta a hibernar entre as checagens.

Armazenamento não é o gargalo: cada vaga com snapshot, índices e tecnologias ocupa
~2,4 kB, e o pipeline só grava snapshot quando algo muda. Em 16/09/2026 os dados
ocupavam ~1,5 MB (9,7 MB com a estrutura do Postgres), e o pior caso, com todas as
~600 vagas mudando a cada coleta, fica em ~22 MB/mês.

**Nada disso é criado pelo repositório.** A conta e o monitor ficam a cargo de quem
opera o projeto.
