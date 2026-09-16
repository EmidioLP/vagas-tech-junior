# Dashboard

Porta de entrada visual do projeto, em [Streamlit](https://streamlit.io). É
**somente leitura**: não coleta, não transforma e não grava nada. Só lê o que o
pipeline já gravou no banco (`jobs`, `job_snapshots`, `job_snapshot_tecnologias`
e `collection_runs`).

## Rodar localmente

```powershell
# tudo do projeto (inclui streamlit)
pip install -r requirements.txt
# ou só o necessário para o dashboard
pip install -r requirements-dashboard.txt

streamlit run dashboard/app.py
```

Abra <http://localhost:8501>.

### De onde vêm os dados

- **`DATABASE_URL`**, lida como no resto do projeto: variável de ambiente >
  `.env.local` (gerado por `neon env pull --service postgres`) > `.env`. Veja
  `docs/neon-setup.md`. Nenhuma URL fica no código, nem em `st.secrets`.
- **`DASHBOARD_DB`** (opcional) aponta para outro banco, URL ou arquivo SQLite, e
  vence a `DATABASE_URL`. É útil para olhar um banco local de teste:

  ```powershell
  $env:DASHBOARD_DB = "data/teste.db"
  streamlit run dashboard/app.py
  ```

O banco precisa estar com `alembic upgrade head` aplicado e ter pelo menos uma
coleta gravada (`python main.py`).

## O que aparece

| Página | Conteúdo | Filtros |
|---|---|---|
| **Overview** | última coleta, agenda e última execução. Na **fotografia atual**: vagas ativas, empresas, % remoto, fontes e distribuição por área, modalidade e fonte | fonte, área, modalidade |
| **Tecnologias** | tecnologias mais citadas nas vagas ativas e o painel "Tecnologias mais pedidas em vagas júnior, por área", sempre em % de uma base declarada | fonte, área, modalidade |
| **Histórico** | por dia de coleta: vagas abertas, vagas abertas por área, vagas novas e snapshots gravados, com a legenda "Como ler estes números" | período, fonte, área, modalidade |
| **Vagas** | tabela paginada (50 por página), com estado atual, primeiro e último avistamento e link | período, fonte, área, modalidade, só ativas |

Os filtros ficam na barra lateral e continuam valendo ao trocar de página. Todos
viram parâmetros da consulta (`IN` e comparações com bind params), nunca texto
interpolado no SQL.

### Definições

A diferença entre **fotografia atual** e **histórico** está em todas as telas:

| Termo | O que conta |
|---|---|
| **Vaga única** | uma linha de `jobs`, identidade `(source, external_id)`. **Toda contagem de "vagas" é de vagas únicas.** Uma vaga com 3 snapshots conta 1 |
| **Vaga ativa** | vaga única com `jobs.is_active = true`. Vagas encerradas (sumiram da listagem em duas coletas completas seguidas) não contam |
| **Snapshot** | uma linha de `job_snapshots`: uma observação da vaga. O pipeline só grava snapshot **quando o estado muda**, então snapshots por dia contam mudanças, não vagas vistas |
| **Estado atual** | o snapshot mais recente da vaga. Dele vêm título, empresa, área e modalidade na Overview, em Tecnologias e em Vagas |
| **Estado vigente num dia** | o último snapshot gravado até o fim daquele dia. Uma vaga que mudou de Backend para Data conta em Backend antes da mudança e em Data depois |
| **Dia de coleta** | dia em UTC com execução `success` ou `partial` (qualquer escopo) em `collection_runs`. Execuções que falharam ou foram puladas não viram ponto |
| **Vagas abertas no dia** | vagas únicas com `first_seen_at` até o fim do dia e sem `closed_at` até lá |
| **Vagas novas no dia** | vagas únicas com `first_seen_at` naquele dia |
| **Último avistamento** | `jobs.last_seen_at`: a coleta mais recente que listou a vaga |
| **Empresas** | nomes distintos entre as vagas ativas, sem diferença de maiúsculas nem espaços nas bordas. Vagas sem empresa não contam |
| **% remoto** | vagas ativas com modalidade Remoto sobre **todas** as vagas ativas, inclusive as que não informam modalidade (a tela mostra quantas são) |
| **Fontes** | portais com pelo menos uma vaga ativa |
| **Base de tecnologias** | vagas ativas do recorte que citam ao menos uma tecnologia. O % de cada tecnologia é sobre essa base |

### Como cada filtro age

- **Fonte, área e modalidade** usam o estado atual na Overview, em Tecnologias e
  em Vagas, e o estado vigente de cada dia no Histórico. Modalidade vazia aparece
  como "Não informado".
- **Período** (dias em UTC, os dois extremos inclusive):
  - no **Histórico**, escolhe os dias de coleta mostrados;
  - em **Vagas**, seleciona as vagas **vistas** no período (primeira vez antes do
    fim e última vez depois do início);
  - na **Overview** e em **Tecnologias** não se aplica, porque elas são a
    fotografia de agora, e a barra lateral avisa.

### Tecnologias: com ressalvas

- **Mede menção, não exigência.** "Diferencial: Python" conta igual a "exige Python".
- **A base é declarada na tela** ("N das M vagas ativas citam alguma tecnologia").
  O card do LinkedIn não traz descrição, então as vagas dele quase nunca entram.
- **Com menos de 30 vagas na base** (`BASE_MINIMA_TECNOLOGIAS`), o ranking geral
  não é mostrado: uma única vaga já mudaria a ordem. A tela pede para ampliar os
  filtros.
- **Por área, cada painel tem a própria base**: as vagas ativas da área que citam
  alguma tecnologia. O gráfico é percentual, não contagem, porque as áreas têm
  tamanhos muito diferentes, e o eixo vai sempre de 0 a 100% para os painéis serem
  comparáveis. Mostra as 8 tecnologias mais citadas de cada área.
  - Base ≥ 30: painel normal.
  - Base de 15 a 29 (`BASE_MINIMA_POR_AREA`): painel marcado como **indicativo**.
  - Base < 15: fora do gráfico, listada abaixo com a base de cada uma.
  Na coleta de 15/09/2026 isso deixou de fora Mobile (13), DevOps (7) e Segurança (7).

### Limitação do histórico

Quando uma vaga encerrada reaparece, o pipeline zera `closed_at`. O encerramento
anterior não fica registrado, então no Histórico ela aparece aberta o tempo todo.

### Estados sem dados

- **Nenhuma coleta registrada:** aviso "Ainda não há coleta registrada".
- **Banco inacessível, sem configuração ou sem schema:** aviso "Dados
  indisponíveis no momento", só com o tipo do erro, em qualquer página. A tela
  nunca mostra URL, usuário, host ou caminho de arquivo.
- **Filtro sem resultado:** aviso para remover filtros, sem gráfico nem métrica zerada.
- **Período sem coleta (Histórico):** aviso com o intervalo em que há coletas.
- **Um único dia de coleta no período:** os números do dia em métricas, sem linha,
  com o aviso de que tendência precisa de pelo menos dois dias.
- **Página além do fim (Vagas):** aviso com o número de páginas.

## Como funciona

```
dashboard/app.py        navegação e cache de cada consulta
dashboard/paginas.py    as quatro páginas e os filtros (sem acesso ao banco)
dashboard/consultas.py  única camada de consultas (SQLAlchemy, só leitura)
dashboard/config.py     engine somente leitura a partir da DATABASE_URL
```

- **Somente leitura de verdade.**
  - PostgreSQL: cada transação é aberta como `READ ONLY` (`postgresql_readonly`),
    o que funciona atrás do pooler do Neon.
  - SQLite: `PRAGMA query_only`.
- **Cache.** O engine é criado uma vez (`st.cache_resource`). Cada consulta fica
  em cache por 10 minutos (`st.cache_data`), com os filtros como chave, e o botão
  *Atualizar dados* na barra lateral limpa o cache. A coleta roda no máximo uma
  vez por dia.
- **Páginas sem engine.** `app.py` entrega às páginas um `paginas.Dados` com as
  consultas já em cache. Os testes trocam esse objeto por fakes.
- **Agrupamento por dia em Python.** A série histórica agrupa por dia UTC em
  Python, porque `date()` sobre `timestamptz` depende do fuso da sessão do banco.
- **Links seguros.** Só URLs `http`/`https` absolutas viram link
  (`consultas.url_segura`). `javascript:`, `data:` e endereços relativos não.
- **Gráficos.** `st.bar_chart` e `st.line_chart`, que já vêm com o Streamlit
  (≥ 1.51, por causa de `horizontal` e `sort`).
- **Dependências mínimas.** A camada de dados não importa FastAPI, requests, bs4
  nem yaml. Um teste garante isso.

## Testes

```powershell
python -m pytest tests/dashboard -q
```

- **`tests/cenario_historico.py`:** histórico conhecido com 4 vagas e 3 dias de coleta,
  mais uma execução que falhou. Uma vaga tem 3 snapshots e muda de Backend para
  Data, outra é encerrada, outra não informa modalidade.
- **`test_analytics.py`:** as análises sobre esse cenário (SQLite com as migrations):
  - vaga única vs. snapshot;
  - estado atual vs. estado vigente;
  - cada filtro, sozinho e combinado, inclusive um valor com cara de injeção;
  - série por dia e período sem coleta;
  - paginação e links seguros;
  - base de tecnologias, geral e por área;
  - banco vazio e banco sem schema.
- **`test_consultas.py`:** o resumo da etapa 07 (última coleta, próxima coleta,
  vagas ativas, recusa de escrita, erro sem vazar caminho).
- **`test_app.py`:** o app renderizado com `streamlit.testing`:
  - Overview completa, com o filtro escolhido chegando na consulta;
  - cada página com dados, vazia, com erro e com as consultas reais no banco de teste.

## Fora desta etapa

Sem camadas Bronze/Silver/Gold, dbt, API analítica nem deploy. O deploy do
dashboard é da etapa 15.
