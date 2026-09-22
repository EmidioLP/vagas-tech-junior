# ADR 0007 — Série histórica reconstruída em Python, com gatilho medido

- **Status:** aceito
- **Data:** 21/09/2026 (issue [#16](https://github.com/EmidioLP/vagas-tech-junior/issues/16))

## Contexto

`dashboard/consultas.py:serie_historica` é a única análise do dashboard que não
agrega no SQL: ela traz `jobs` e `job_snapshots` para a memória e reconstrói cada
dia de coleta em Python. O motivo está no código desde o começo — o agrupamento
por dia precisa ser em UTC, e `date()` sobre `timestamptz` depende do fuso da
sessão, que atrás do pooler do Neon não é estável.

A pergunta da issue era quando isso deixa de caber. A suspeita registrada em
[0005](0005-render-e-streamlit-community-cloud.md) e em `../deploy.md` era
**memória**: o Streamlit Community Cloud tem cerca de 1 GB. A medição mostrou que
a suspeita estava errada, e que o custo real era outro.

**Volume de referência** (logs do workflow de coleta, execuções de 17/09 e
19/09/2026): ~600 vagas ativas, uma coleta a cada 2 dias, ~55 vagas e ~67
snapshots novos por coleta. Nada é apagado.

**Medição** (`scripts/medir_serie_historica.py`, 21/09/2026, Windows 11, Python
3.13, SQLite local, período completo — que é o padrão da tela):

| Histórico | Volume | Antes | Depois | Pico de memória |
|---|---|---|---|---|
| 180 dias | 5.495 vagas, 6.469 snapshots, 90 dias de coleta | 2,716s | 0,625s | 5,8 MB |
| 365 dias | 10.555 vagas, 12.526 snapshots, 182 dias | 9,416s | 1,316s | 10,5 MB |
| 730 dias | 20.620 vagas, 24.619 snapshots, 365 dias | 35,017s | 3,165s | 20,3 MB |

Contra a **`dados-main`** (21/09/2026, 714 vagas, 737 snapshots, 3 dias de
coleta): **0,615s e 0,6 MB**.

Esse 0,6s é quase todo **rede**, não CPU: a função faz três consultas em sequência
ao Neon, e o trabalho em memória são ~2.100 iterações, coisa de milissegundos.
Ele serve como **piso** — toda medição futura na `dados-main` carrega esses ~0,6s
de ida e volta antes de qualquer trabalho de CPU.

Cuidado ao ler a tabela acima junto com esse número: 0,615s na `dados-main` e
0,625s no sintético de 180 dias são quase iguais e não têm nada a ver um com o
outro. O primeiro é latência de rede com 3 pontos na série; o segundo é CPU local,
em SQLite, com 90. Comparar os dois diretamente leva à conclusão errada.

Duas leituras dos números:

- **Memória nunca foi o gargalo.** São 3 colunas de `jobs` e 4 de `job_snapshots`;
  20 MB depois de dois anos, contra ~1 GB disponíveis. O limite de memória seria
  atingido daqui a décadas.
- **O custo era CPU, e crescia ao quadrado no tempo.** O laço era `para cada dia,
  para cada vaga` — O(dias × vagas). Como o período padrão da tela é o histórico
  inteiro (`dashboard/paginas.py`, o `date_input` já nasce com
  `primeiro_dia..ultimo_dia`), *dias* e *vagas* crescem juntos: dobrar o histórico
  quadruplicava o tempo (2,7s → 9,4s → 35,0s). O cache de 10 minutos só adia isso:
  a primeira carga depois do TTL paga a conta inteira.

## Decisão

- **O agrupamento continua em Python.** Nada de SQL novo, tabela agregada ou
  migration: o motivo do fuso horário não mudou, e no volume atual o SQL resolveria
  um problema que não existe.
- **A varredura passou a ser por vaga, não por dia.** Cada vaga visita só os dias
  entre a estreia e o encerramento, com um ponteiro que avança sobre os próprios
  snapshots em vez de um `bisect` por dia. O custo passa a ser a soma dos tempos de
  vida das vagas, que é linear no número de dias porque a quantidade de vagas
  *abertas ao mesmo tempo* é estável (~600). Dobrar o histórico passou a custar
  ~2,4× em vez de ~3,7×.
- **Gatilho para migrar, explícito:** revisitar esta decisão quando a série do
  período completo passar de **5 segundos contra a `dados-main`**
  (`DASHBOARD_DB=<url da dados-main> python scripts/medir_serie_historica.py`), ou
  quando o histórico passar de **500 dias de coleta**. Pelos números acima isso são
  cerca de 3 anos de coleta a cada 2 dias.

  A medição que vale é a da `dados-main`, não a do `--projetar`: é ela que inclui a
  rede, que é o que a pessoa na tela espera de fato. Os ~0,6s de piso fazem parte do
  orçamento — o gatilho dispara com ~4,4s de CPU, não 5. O `--projetar` serve para
  antecipar a curva, não para decidir.

  Os 500 dias são só o lembrete de refazer a medição, para o gatilho não depender de
  alguém lembrar sozinho.
- **A semântica é intocável.** Vaga aberta = `first_seen_at` antes do fim do dia e
  sem `closed_at` até ali, com área e modalidade do snapshot vigente no fim do dia.
  `tests/dashboard/test_analytics.py` fixa os valores exatos e não mudou.
- **O laço antigo virou oráculo**, em
  `scripts/medir_serie_historica.py:serie_referencia`. Ele não é código vivo: existe
  para provar que a varredura concorda com a versão que já rodou em produção.
  `tests/dashboard/test_serie_equivalencia.py` o roda sobre um histórico sintético,
  e `python scripts/medir_serie_historica.py --comparar` o roda sobre um banco de
  verdade, conferindo ponto a ponto todos os filtros que existem naquele banco
  (cada fonte, cada área, cada modalidade, recortes de período). Sai 1 se divergir,
  e nunca imprime URL, host ou usuário — só contagens e o tipo do erro.
  **Executado em 21/09/2026 contra a `dados-main`** (714 vagas, 737 snapshots, 3
  dias de coleta): 28 filtros conferidos, séries idênticas em todos. O mesmo
  comando rodou sobre um histórico sintético de 2 anos (365 dias de coleta, 20.620
  vagas): 28 filtros, idênticas.

## Consequências

- **Ganha:** três anos de margem sem mudar a arquitetura de leitura; o gatilho é um
  comando que qualquer um roda, não uma impressão; o código continua em Python,
  testável sem banco de verdade e sem a armadilha de fuso do `date()` no SQL; e a
  troca é verificável contra os dados reais, não só contra o cenário de teste.
- **Custa:**
  - a consulta de snapshots tem só limite superior (`collected_at < limite`), sem
    limite inferior: estreitar o período **não** reduz o volume carregado. Corrigir
    exige recuperar, por vaga, o último snapshot anterior à janela
    (`row_number() over (...)`), e não traz ganho nenhum no caminho padrão, em que o
    período já é o histórico inteiro. Fica registrado, não implementado;
  - a varredura por janela é mais difícil de ler que o laço por dia. Ela só se
    justifica pelos números acima, e obriga a manter o laço antigo vivo como
    oráculo — código que ninguém executa em produção mas que não pode ser apagado;
  - a medição é manual. Nada no CI falha quando o tempo cresce: alguém precisa
    rodar o script. O `--comparar` contra a `dados-main` também é manual, porque o
    CI não tem (nem deve ter) credencial de banco;
  - as taxas de crescimento do `--projetar` vieram de duas coletas. Se o perfil do
    histórico mudar (vagas vivendo muito mais, ou muito mais fontes), a projeção
    precisa ser refeita antes de valer como gatilho;
  - o `--comparar` na `dados-main` só pôde conferir 3 dias de coleta: o histórico
    ainda é novo. Ele fica mais forte a cada coleta, e vale repetir depois de
    algumas dezenas de dias — é barato e não escreve nada.

## O que mudaria a decisão

- O gatilho acima: mais de 5s na série do período completo, ou mais de 500 dias de
  coleta. Aí o agrupamento vai para SQL ou para uma tabela agregada por dia de
  coleta, preservando a mesma semântica e com o teste de equivalência já pronto
  para validar.
- Vagas com vida muito mais longa, que fariam a base aberta crescer em vez de se
  estabilizar: nesse caso a varredura por janela volta a ser quadrática.
- Um filtro de período usado de verdade (hoje o padrão é o histórico inteiro): aí o
  limite inferior ausente na consulta de snapshots passa a valer o trabalho.
- Refinamento numérico do gatilho qualitativo de
  [0004](0004-sem-medalhao-nem-dbt.md) ("consultas históricas lentas"), que continua
  valendo para o resto do projeto.

## Nota de 22/09/2026 — a cadência mudou

A medição e o volume de referência acima assumem **uma coleta a cada 2 dias**. O
[ADR 0009](0009-coleta-diaria.md) passou a coleta para diária, e "dias de coleta"
é exatamente a grandeza que dobra: os "cerca de 3 anos" do gatilho de 500 dias
passam a ser **~1,4 ano**, e o tempo de CPU da série ~dobra para o mesmo intervalo
de calendário, porque a varredura por vaga soma tempos de vida medidos em dias de
coleta. A decisão desta ADR não muda — muda o prazo. Vale refazer a medição contra
a `dados-main` depois de algumas dezenas de coletas diárias, como o próprio texto
acima já pedia para quando "o perfil do histórico mudar".
