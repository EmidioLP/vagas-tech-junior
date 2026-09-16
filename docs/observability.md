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

Com X = 2, o dado vence a partir de **5 dias** sem coleta completa, o que tolera uma
coleta perdida. `coleta_parada` aparece antes: o cron acorda todo dia e registra até
as execuções puladas, então dois dias sem nenhuma linha em `collection_runs`
significam agendamento parado.

A resposta nunca traz URL, host, usuário nem mensagem do driver:

```json
{
  "estado": "em_dia",
  "saudavel": true,
  "ultima_coleta": "2026-09-15T22:01:58Z",
  "status_ultima_coleta": "partial",
  "dias_desde_ultima_coleta": 1,
  "intervalo_dias": 2,
  "limite_dias": 4,
  "ultima_execucao": "2026-09-16T13:55:40Z",
  "status_ultima_execucao": "skipped",
  "dias_desde_ultima_execucao": 0,
  "proxima_coleta": "2026-09-17"
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
  escopo completo? Então é o caso 1 ou coletas manuais parciais.
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
UptimeRobot (plano free, checagem a cada 5 minutos):

1. Criar a conta e um monitor do tipo HTTP(s) para
   `https://vagas-tech-junior-api.onrender.com/health/dados`.
2. Alertar quando o status não for 2xx, com e-mail como canal.
3. Tolerar o primeiro timeout. O Render pode levar ~50s para acordar, então alerte
   só depois de 2 falhas seguidas, se o plano permitir.

Efeito colateral: checar a cada 5 minutos mantém o serviço do Render acordado. Um
único serviço 24 horas por dia cabe nas 750 h/mês do plano free, mas soma com
qualquer outro serviço free da mesma conta.

**Nada disso é criado pelo repositório.** A conta e o monitor ficam a cargo de quem
opera o projeto.
