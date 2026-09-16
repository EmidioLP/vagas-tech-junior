# Prompt 12 — Frescor dos dados e monitoramento

**Entrega:** API e dashboard dizem quando o dado está vencido, e existe um jeito documentado de perceber que a coleta parou de rodar, inclusive quando o workflow nem dispara.

> **A falha que ninguém vê:** coleta que falha deixa um vermelho no Actions. Coleta que **deixa de rodar** não deixa nada. O GitHub desativa agendamentos de repositórios sem atividade por 60 dias, e o dashboard seguiria exibindo números antigos como se fossem atuais.

---

## O que mostrar antes

Mostre o que `/health` responde hoje, o que o dashboard mostra sobre a última coleta e o que acontece com os dois se nenhuma coleta rodar por uma semana (simule em teste com datas).

## Contexto e objetivo

`collection_runs` já registra status, motivo, contagens por fonte e `next_run_on`; o log de falha já sai sanitizado. Esta etapa não cria uma pilha de observabilidade. Ela transforma o que já está registrado em sinais de frescor e alerta, proporcionais ao projeto.

## Analise exatamente isto

- `api/app.py` (`/health`), `render.yaml` (`healthCheckPath`) e `dashboard/consultas.py` (`ultima_coleta`, `proxima_coleta`).
- `.github/workflows/collect.yml`, `docs/automation.md` e o intervalo `COLLECTION_INTERVAL_DAYS`.
- Como os logs do pipeline identificam uma execução (hoje não há `run_id` comum a log, resumo e `collection_runs`).

## Implemente somente isto

1. Regra pura de frescor: dado vencido quando a última coleta de escopo completo (`success`/`partial`) é mais antiga que um limite derivado do intervalo (ex.: 2× X dias), sem valor mágico escondido.
2. Na API: `/health` continua sendo liveness e responde 200 se o processo e o banco respondem; um endpoint separado (ex.: `/health/dados`) informa última coleta, próxima prevista, status e se está vencido, sem expor URL, host ou erro bruto.
3. No dashboard: aviso visível quando o dado está vencido, usando a mesma regra.
4. Correlação: o id de `collection_runs` (e `GITHUB_RUN_ID` quando houver) aparece no log, no resumo e no registro da execução.
5. Monitor de frescor independente do agendamento da coleta. Documente a opção escolhida; recomendado um monitor externo gratuito sobre `/health/dados`, configurado à mão. Registre em `docs/observability.md` sinais, limites, playbook (todas as fontes falharam, alerta de qualidade, dado vencido, agendamento desativado) e o que é manual.

## Arquivos/áreas esperados para revisão

`api/`, `dashboard/`, `scraper/pipeline.py`, workflow, testes e `docs/observability.md`.

## Tecnologias envolvidas

FastAPI, Streamlit, GitHub Actions, Python logging, PostgreSQL.

## Como verificar a entrega

1. Com a última coleta completa dentro do limite, `/health/dados` diz "em dia"; fora dele, "vencido", e o dashboard mostra o aviso.
2. `/health` continua 200 com dado vencido.
3. Um mesmo id liga log, resumo do Actions e linha de `collection_runs`.
4. `docs/observability.md` diz o que fazer em cada cenário do playbook.

## Armadilha importante

O Render usa `/health` para decidir se o serviço está saudável. Se ele responder erro por dado vencido, o Render reinicia ou derruba uma API que está funcionando, e o problema não é a API. Liveness e frescor são sinais diferentes e ficam em endpoints diferentes.

## Restrições

- Sem Prometheus, Grafana, OpenTelemetry ou serviço pago.
- Não crie conta externa nem configure o monitor sem pedido explícito; só documente o passo manual.
- Nunca registre `DATABASE_URL`, tokens ou payloads completos.
- Não altere a política de intervalo nem as regras de qualidade da etapa 11.

## Testes

Teste a regra de frescor nos limites (exatamente no limite, sem coleta alguma, só coletas `failed` ou parciais de escopo), os endpoints de health, o aviso do dashboard e a presença do id de correlação. Rode a suíte completa.

## Critérios de conclusão

- Dado vencido é visível para quem usa a API ou o dashboard.
- A coleta parada é detectável mesmo sem nenhuma execução acontecer.

## Encerramento obrigatório

Mostre respostas de exemplo dos endpoints (sanitizadas), o aviso do dashboard e os testes. **PARE. Não configure serviço externo nem reescreva a documentação geral.**
