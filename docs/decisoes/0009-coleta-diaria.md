# ADR 0009 — Coleta diária, em vez de a cada dois dias

- **Status:** aceito
- **Data:** 22/09/2026

## Contexto

O `collect.yml` tem um cron diário (`0 9 * * *`) que só **acorda** o workflow;
quem decide se coleta é a guarda de intervalo, com X vindo da Repository Variable
`COLLECTION_INTERVAL_DAYS`. Até aqui X era **2**, então em metade dos dias a
execução era registrada como `skipped` e terminava em ~40 s sem acessar nenhum
portal. Medido nas execuções de 15 a 21/09/2026: quando coleta de fato, o job
leva **~13 minutos**; quando pula, ~40 s.

A frequência foi desenhada como parâmetro justamente para poder mudar
([`../automation.md`](../automation.md#frequência-cron-diário--guarda-de-intervalo)):
`scraper/execucao.py` só exige `intervalo_dias >= 1`, e `Agenda.periodicidade` já
tinha o caso `"a cada 1 dia"` escrito. Nenhum teste fixa o valor de X — os que o
mencionam passam o número explicitamente ou fixam o mecanismo (`vars`, nunca
`secrets`).

Duas restrições que **não** pesam neste caso, e que foram conferidas antes:

- **Minutos do Actions:** o repositório é público, então os minutos são
  ilimitados e gratuitos. Dobrar o tempo de execução mensal (~195 min → ~390 min)
  não tem custo.
- **Armazenamento no Neon:** um snapshot só nasce quando o `content_hash` muda, e
  a quantidade de vagas **novas por mês** não depende da cadência. Medido nos
  snapshots reais (~2 KB cada, descrição de ~1.700 caracteres), dois anos de
  histórico ficam em ~48 MB; mesmo o cenário pessimista de snapshots dobrando dá
  ~96 MB, contra os 0,5 GB do free tier.

## Decisão

`COLLECTION_INTERVAL_DAYS = 1`. A coleta completa passa a rodar todo dia.

Com X=1 a guarda não deixa de existir: ela continua barrando uma **segunda**
execução agendada no mesmo dia UTC, que é o caso para o qual foi escrita
(comparar datas, e não horas, para o cron não "escorregar").

Nenhum arquivo de código muda de comportamento. A mudança é
`gh variable set COLLECTION_INTERVAL_DAYS --body 1`.

## Consequências

- **Ganha:** o dado fica no máximo um dia atrás do portal, em vez de dois; e
  `closed_at` fica mais perto do fim real do anúncio — a regra de encerramento
  continua exigindo **duas** ausências em dias UTC diferentes (a proteção contra
  vaga que caiu fora das 5 páginas segue intacta), mas o relógio comprime de ~4
  dias para ~2.

- **Custa:**

  - **a régua do frescor aperta.** `persistence/frescor.py` calcula
    `limite = X × MULTIPLO_DO_INTERVALO` (=2): o dado vencia com mais de 4 dias e
    passa a vencer com mais de 2. A tolerância continua sendo de **uma** coleta
    perdida, mas a janela de relógio cai de 5 para 3 dias. Como `/health/dados`
    responde **503** em `vencido` e o dashboard mostra `st.warning`, duas
    execuções agendadas descartadas pelo GitHub em seguida passam a acender o
    alerta — antes não acendiam;

  - **`coleta_parada` deixa de aparecer antes de `vencido`.** Os dois limiares se
    encontram: `vencido` passa a ser 2 × 1 = 2 dias e `coleta_parada` continua
    sendo 2 dias (`DIAS_SEM_EXECUCAO` não depende de X), então no cenário de cron
    parado os dois acendem no 3º dia e `vencido` ganha por vir primeiro na cadeia
    de `if` (`persistence/frescor.py:106-109`). Com X=2, `coleta_parada` acendia no
    3º dia e `vencido` só no 5º — o aviso de "cron morreu" vinha antes do dado
    estragar, e era uma propriedade declarada em
    [`../observability.md`](../observability.md). **Aceitamos a perda:** os dois
    estados respondem 503 e estão em `ESTADOS_COM_PROBLEMA`, então nenhum alerta
    some; o que some é o rótulo mais específico, e a mesma resposta já carrega
    `dias_desde_ultima_execucao` e `status_ultima_execucao` para separar um caso do
    outro. Mexer nas constantes para recuperar o rótulo sairia caro: baixar
    `DIAS_SEM_EXECUCAO` para 1 faria uma única execução descartada pelo GitHub
    acender alarme, e subir `MULTIPLO_DO_INTERVALO` para 3 passaria a tolerar duas
    coletas perdidas em vez de uma, afrouxando justamente a régua que a coleta
    diária deveria apertar;

  - **a vida observada das vagas cai sem o mercado mudar.** As vagas gravadas
    antes de 22/09/2026 foram encerradas pela régua de ~4 dias e não são
    recalculadas. A contagem de "vagas ativas" tende a baixar em regime, e quem
    ler a série histórica atravessando esta data vê uma quebra que é de método,
    não de mercado ([`../limitacoes.md`](../limitacoes.md#frequência));

  - **o gatilho do ADR [0007](0007-serie-historica-em-python.md) chega na metade
    do tempo.** Ele é "500 dias de coleta… cerca de 3 anos de coleta a cada 2
    dias". Dias de coleta é exatamente o que dobra: passa a ser **~1,4 ano**. A
    varredura por vaga custa a soma dos tempos de vida medidos em dias de coleta,
    então o tempo de CPU da série também ~dobra para o mesmo intervalo de
    calendário;

  - **a carga nos portais dobra.** São os mesmos 13 termos × 7 fontes × até 5
    páginas, agora todo dia, contra portais que não deram permissão nenhuma. O
    delay de 1,5 s com jitter, o backoff e o User-Agent identificável continuam
    valendo ([`../fontes.md`](../fontes.md#educação-com-o-servidor)), mas a
    decisão de dobrar a frequência é explícita, não implícita;

  - **a janela da queda brusca encolhe.** `historico_vagas_brutas(limite=5)` olha
    as 5 últimas coletas completas: eram 10 dias, passam a ser 5. A mediana fica
    mais local — mais sensível a quebra recente, menos capaz de enxergar um
    declínio lento de dez dias. `FRACAO_MINIMA_DA_MEDIANA`, `HISTORICO_MINIMO` e
    `MEDIANA_MINIMA` não foram mexidos: recalibrar sem dado seria adivinhar. Se
    aparecerem falsos positivos, o ajuste certo é subir o `limite` de
    `persistence.execucoes.historico_vagas_brutas` de 5 para 7-10, para manter a
    janela de calendário perto dos 10 dias de antes, e não afrouxar a fração;

  - **as taxas de `scripts/medir_serie_historica.py` ficam desatualizadas, e não
    foram mexidas.** `VAGAS_POR_COLETA = 55`, `MUDANCAS_POR_COLETA = 12` e
    `VIDA_MINIMA/MAXIMA` são **por coleta**, medidas nas execuções de 17 e
    19/09/2026 com cadência de 2 dias. Trocar só `DIAS_ENTRE_COLETAS` para 1
    dobraria o mercado sintético (55 vagas novas por dia em vez de por 2 dias), que
    é falso. O bloco fica como está, com a medição antiga, até haver algumas
    dezenas de coletas diárias para re-medir as quatro constantes juntas — é
    exatamente a ressalva que o [0007](0007-serie-historica-em-python.md) já fazia.

## O que mudaria a decisão

- **`vencido` acendendo sem coleta realmente parada**, por execução agendada
  descartada pelo GitHub. O problema aí é a régua, não a frequência, e a correção
  é subir `MULTIPLO_DO_INTERVALO` para 3 em `persistence/frescor.py` — uma mudança
  de código, com teste. Isso passa a tolerar duas coletas perdidas em vez de uma,
  o que hoje recusamos por antecipação (acima), mas aceitaríamos **de posse do
  dado** de que o GitHub descarta execuções com frequência suficiente. O efeito
  colateral é bem-vindo: com `limite = 3`, `coleta_parada` volta a aparecer antes
  de `vencido`.
- **Um portal reclamando ou passando a bloquear** depois da mudança. Aí X volta
  para 2 alterando só a Variable, e o motivo entra em
  [`../fontes.md`](../fontes.md).
- **O gatilho do [0007](0007-serie-historica-em-python.md) disparar** (mais de 5 s
  na série do período completo contra a `dados-main`). Aí o caminho é migrar o
  agrupamento para SQL, como aquele ADR já descreve — não coletar menos.
