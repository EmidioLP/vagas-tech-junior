# Dashboard

Porta de entrada visual do projeto, em [Streamlit](https://streamlit.io). É
**somente leitura**: não coleta, não transforma e não grava nada. Só lê o que o
pipeline já gravou no banco (`jobs` e `collection_runs`).

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

| Página | Conteúdo |
|---|---|
| **Overview** | vagas ativas, data e hora da última coleta completa bem-sucedida, "Última coleta: dia … e próxima: dia …" e a última execução (inclusive puladas ou com falha) |
| Tecnologias | em construção (etapa 08) |
| Histórico | em construção (etapa 08) |
| Vagas | em construção (etapa 12) |

- **Vagas ativas:** `jobs` com `is_active = true`. Vagas encerradas (que sumiram
  da listagem em duas coletas seguidas) não contam.
- **Última coleta:** a mesma regra da guarda de intervalo. Vale a última execução
  de escopo completo com status `success` ou `partial`.
- **Próxima coleta:** o `next_run_on` gravado pela execução mais recente.
- **Horários:** em Brasília (UTC-3). As datas da agenda de coleta ficam em UTC,
  como no resto da automação (`docs/automation.md`).

### Estados sem dados

- **Nenhuma coleta registrada:** aviso "Ainda não há coleta registrada".
- **Banco inacessível, sem configuração ou sem schema:** aviso "Dados
  indisponíveis no momento", só com o tipo do erro. A tela nunca mostra URL,
  usuário, host ou caminho de arquivo.

## Como funciona

```
dashboard/app.py        navegação, cache e página de entrada
dashboard/paginas.py    apresentação (sem acesso ao banco)
dashboard/consultas.py  única camada de consultas (SQLAlchemy, só leitura)
dashboard/config.py     engine somente leitura a partir da DATABASE_URL
```

- **Somente leitura de verdade.**
  - PostgreSQL: cada transação é aberta como `READ ONLY` (`postgresql_readonly`),
    o que funciona atrás do pooler do Neon.
  - SQLite: `PRAGMA query_only`.
- **Cache.** O engine é criado uma vez (`st.cache_resource`). O resumo fica em
  cache por 10 minutos (`st.cache_data`), e o botão *Atualizar dados* na barra
  lateral limpa o cache. A coleta roda no máximo uma vez por dia.
- **Dependências mínimas.** A camada de dados não importa FastAPI, requests nem
  bs4. Um teste garante isso.

## Testes

```powershell
python -m pytest tests/dashboard -q
```

- **`test_consultas.py`:** as consultas contra um SQLite com as migrations
  aplicadas:
  - estado vazio;
  - regra da última coleta;
  - próxima coleta;
  - vagas ativas;
  - recusa de escrita;
  - erro sem vazar caminho.
- **`test_app.py`:** o app renderizado com `streamlit.testing`:
  - com dados;
  - vazio;
  - com erro;
  - páginas futuras.

## Fora desta etapa

Sem gráficos, analytics nem deploy. O deploy do dashboard é da etapa 15.
