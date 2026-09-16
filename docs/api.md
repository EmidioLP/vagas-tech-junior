# API, banco e deploy

A API REST somente leitura, como rodá-la com Docker, como o banco é configurado e
como a API é publicada. Visão geral em [`architecture.md`](architecture.md);
decisões de hospedagem em
[`decisoes/0005-render-e-streamlit-community-cloud.md`](decisoes/0005-render-e-streamlit-community-cloud.md).

Há uma API **somente leitura** sobre os dados coletados. Ela não substitui o
pipeline: as vagas continuam entrando pelo scraper, e a API só as expõe por HTTP.

Ela lê o **histórico que a coleta grava** (`jobs` + `job_snapshots`), com a mesma
regra do dashboard: cada vaga única aparece com o estado da coleta mais recente
em que foi vista, e as contagens consideram só as vagas ativas. Para o mesmo
banco, API e dashboard mostram os mesmos números (há teste que garante isso).

**No ar em [vagas-tech-junior-api.onrender.com/docs](https://vagas-tech-junior-api.onrender.com/docs)**
(primeiro acesso pode levar ~1 min — o plano gratuito hiberna).

Para rodar na sua máquina, configure antes a `DATABASE_URL` (veja [Banco](#banco)
e [docs/neon-setup.md](neon-setup.md)):

```bash
pip install -r requirements.txt
```

```bash
uvicorn api.app:app --reload
```

O banco precisa ter o schema (`alembic upgrade head`) e pelo menos uma coleta
gravada (`python main.py`).

Documentação interativa em **http://127.0.0.1:8000/docs** (`127.0.0.1` é a sua
própria máquina).

## Endpoints

| Método | Rota | O que faz |
|---|---|---|
| GET | `/vagas` | Lista vagas ativas. Filtros: `area`, `tecnologia`, `modalidade`, `fonte`, `q` (título), `incluir_encerradas`, `limit`, `offset` |
| GET | `/vagas/{id}` | Detalhe da vaga, ativa ou encerrada, com descrição completa e ciclo de vida (`ativa`, `first_seen_at`, `last_seen_at`, `closed_at`) |
| GET | `/areas` | As 10 áreas com contagem de vagas ativas e percentual |
| GET | `/areas/{nome}` | Uma área |
| GET | `/tecnologias` | As 114 tecnologias com contagem de vagas ativas que as citam. Filtros: `grupo`, `com_vagas` |
| GET | `/tecnologias/{nome}` | Uma tecnologia |
| GET | `/health` | Liveness: processo e banco respondem (é o health check do Render) |
| GET | `/health/dados` | Frescor dos dados: 200 em dia, **503** se vencidos ou se a coleta parou ([docs/observability.md](observability.md)) |

Exemplos, contra a instância pública:

```bash
curl "https://vagas-tech-junior-api.onrender.com/vagas?area=Backend&modalidade=Remoto&limit=5"
```

```bash
curl "https://vagas-tech-junior-api.onrender.com/tecnologias?grupo=linguagens&com_vagas=true"
```

**Não há `POST`, `PUT` nem `DELETE`** — os dados vêm da raspagem, e escrever por
HTTP criaria um estado que a próxima coleta sobrescreveria. Esses verbos
respondem `405`.

Erros: `404` para vaga/área/tecnologia inexistente, `422` para parâmetro fora do
vocabulário (`?area=Inexistente`), sempre no formato `{"detail": "..."}`.

**Mudanças de contrato (setembro de 2026).** Até então a API lia a tabela `vagas`,
importada de um CSV. Ao passar a ler o histórico:

- o `id` de `/vagas/{id}` passou a ser o da vaga única (`jobs.id`). Ids antigos
  podem dar 404 ou apontar para outra vaga;
- saíram `created_at`, `updated_at` (datas da importação) e `search_term` (não é
  gravado no histórico); entraram `ativa`, `first_seen_at`, `last_seen_at` e
  `closed_at`;
- `/vagas`, `/areas` e `/tecnologias` passaram a considerar só vagas ativas.

## Docker (API + PostgreSQL)

Sobe a API e um PostgreSQL juntos, sem instalar nada além do Docker:

```bash
docker compose up --build
```

Pronto — **http://localhost:8000/docs**. O primeiro build leva ~1 min; depois
sobe em segundos.

O que acontece no `up`: o Postgres sobe, a API espera ele ficar **realmente**
pronto (healthcheck com `pg_isready`, não apenas o container existir), aplica as
migrations (`alembic upgrade head`), carrega `seed/vagas.csv` no histórico e só
então inicia o uvicorn. Não precisa de rede: o seed entra como se fosse a coleta
de 15/09/2026.

```bash
docker compose down
```

Para apagar também os dados do banco, use `docker compose down -v`.

O banco fica num volume, então parar e subir de novo preserva os dados — e como
a carga é idempotente, subir de novo não duplica nada. Dá para inspecionar o
Postgres de fora, na porta 5432:

```bash
docker compose exec db psql -U vagas -d vagas -c "SELECT source, COUNT(*) FROM jobs WHERE is_active GROUP BY source ORDER BY 2 DESC;"
```

## Banco

O banco é configurado por **uma única variável, `DATABASE_URL`**, que aponta
para um PostgreSQL — o destino é o [Neon](neon-setup.md). Ela é procurada
nesta ordem:

1. variável já definida no ambiente — é o que o `docker-compose` define;
2. `.env.local`, gerado por `neon env pull --service postgres`;
3. `.env`, legado.

**Sem `DATABASE_URL`, a API, a coleta e a carga do seed falham na inicialização**, com
mensagem clara, em vez de cair num banco padrão. Nenhum desses arquivos é
versionado; o `.env.example` mostra o formato com valores fictícios. O passo a
passo do Neon está em [docs/neon-setup.md](neon-setup.md).

A carga do seed aceita um destino explícito, que vence a variável — inclusive um
arquivo SQLite já migrado, útil para ter dados locais sem coletar:

```bash
python scripts/carregar_seed.py --db postgresql://vagas:vagas@localhost:5432/vagas
```

Ela grava o CSV pela mesma persistência da coleta e **recusa bancos que já têm
execuções em `collection_runs`**: num banco com coletas reais, o seed viraria
snapshots falsos no passado.

URLs com o prefixo histórico `postgres://` (que Render e Heroku ainda entregam,
e que o SQLAlchemy recusa) são convertidas automaticamente. A senha nunca
aparece nos logs.

Um SQLite local via `--db data/local.db` fica ignorado pelo git — é reconstruível
com `alembic upgrade head` e a carga do seed.

Duas decisões de modelagem que valem menção:

- **`skills` vira relação.** A lista de tecnologias de cada vaga é gravada numa
  tabela `tecnologias` + associação muitos-para-muitos com o snapshot. Sem isso
  não dá para filtrar nem contar direito.
- **`/areas` e `/tecnologias` são calculados do banco** (vagas ativas no estado
  atual), nunca lidos de `ranking_areas.csv` ou `skills_por_area.csv`. Esses CSVs são recortes já
  agregados — o de skills é truncado no top-15 de cada área, então serviria
  números errados.

## Datas

Os portais escrevem a data de publicação em três formatos: ISO (`2026-06-26`,
Gupy), `dd/mm/aaaa` (Vagas.com) e relativo (`"Ontem"`, `"Há 3 dias"`, Vagas.com).
A persistência converte tudo para um único campo `DATE`.

As expressões relativas são resolvidas contra o **dia da coleta**, não contra a
data de hoje. Por isso a carga do seed usa a data fixa da coleta que gerou o CSV
(`DATA_DO_SEED` em `scripts/carregar_seed.py`, ou `--coletado-em`): carregar o
seed em qualquer dia produz as mesmas datas.

## Deploy

`render.yaml` sobe a API no [Render](https://render.com) — basta apontar o
serviço para o repositório.

O banco é o **Neon** (branch `dados-main`). A `DATABASE_URL` fica só no painel do
Render; o `render.yaml` declara a variável sem valor. O boot só sobe a API, que
lê o histórico gravado pela coleta automática no mesmo banco.
O build usa `requirements-api.txt`, sem matplotlib, que a API nunca importa.

O scraper **não roda no servidor da API**, de propósito: portais de vaga
costumam bloquear IP de nuvem. A coleta automática roda no GitHub Actions
(`docs/automation.md`). Branches Neon, variáveis e migrations em produção:
`docs/neon-setup.md`.

Cada coleta passa por **checagens de qualidade** antes de ser considerada
confiável. Um portal que volta zerado sem erro, uma queda brusca ou valores fora
do domínio deixam o job vermelho, e a fonte afetada não encerra vagas. Regras,
limites e ações: [`docs/data-quality.md`](data-quality.md).

No plano free o serviço hiberna após 15 minutos parado, e o primeiro acesso
depois disso leva ~50s para responder.
