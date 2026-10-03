# Docker (uso local)

O projeto inteiro na máquina, sem instalar Python nem configurar banco, e sem
nenhum segredo. É só para uso local: o deploy publicado não usa estas imagens (a
API roda no Render com `requirements-api.txt`, o dashboard no Streamlit Community
Cloud e a coleta no GitHub Actions — ver [`architecture.md`](architecture.md)).

## Subir API e dashboard

```bash
docker compose up --build
```

- API: **http://localhost:8000/docs**
- Dashboard: **http://localhost:8501**

O que acontece no `up`:

1. `db` — PostgreSQL 16, com os dados num volume (`postgres_data`).
2. `preparo` — espera o Postgres ficar **realmente** pronto (healthcheck com
   `pg_isready`, não apenas o container existir), aplica as migrations
   (`alembic upgrade head`), carrega `seed/vagas.csv` no histórico e termina.
3. `api` e `dashboard` — só sobem depois que o `preparo` termina com sucesso.

Não precisa de rede: o seed entra como se fosse a coleta de 15/09/2026. A carga é
idempotente, então parar e subir de novo não duplica nada.

`GET /health/dados` responde **503** aqui, e o dashboard mostra "Última coleta: —":
o seed não cria linha em `collection_runs`, então o frescor é `sem_coleta`. Só uma
coleta de escopo completo muda isso. `/health` responde 200 normalmente.

```bash
docker compose down        # para tudo, mantém o banco
docker compose down -v     # apaga também os dados do banco
```

Dá para inspecionar o Postgres de fora, na porta 5432:

```bash
docker compose exec db psql -U vagas -d vagas -c "SELECT source, COUNT(*) FROM jobs WHERE is_active GROUP BY source ORDER BY 2 DESC;"
```

## Coletar (sob demanda)

A coleta fica fora do `up` de propósito: ela faz requisições de verdade aos
portais, a partir do IP da sua máquina, e leva minutos. Os argumentos são os de
`python main.py`:

```bash
docker compose run --rm coleta --sources gupy --max-pages 1
docker compose run --rm coleta --sources gupy --max-pages 1 --csv --resumo coleta/resumo.md
```

Ela grava no Postgres do compose, então a API e o dashboard passam a mostrar o
resultado (o dashboard guarda cache por 10 minutos). Os arquivos de `--csv` e
`--resumo` caem em `./output` e `./coleta` da máquina. Vale a etiqueta de
[`fontes.md`](fontes.md): para experimentar, poucas fontes e poucas páginas.

Depois da primeira coleta, o banco local tem linhas em `collection_runs`, e o
`preparo` deixa de carregar o seed nos próximos `up` (ele viraria snapshots falsos
no passado do histórico). As migrations continuam sendo aplicadas. Para voltar ao
seed limpo: `docker compose down -v`.

`--respect-interval` precisa de `COLLECTION_INTERVAL_DAYS`, que o compose não
define: passe com `docker compose run --rm -e COLLECTION_INTERVAL_DAYS=1 coleta --respect-interval`.

## Testes

```bash
docker compose run --rm testes                              # a suíte inteira
docker compose run --rm testes tests/test_classifier.py -q  # argumentos vão para o pytest
```

Roda em Python 3.11, uma das versões do CI, com o container **sem rede**
(`network_mode: none`): se um teste tentar acessar um portal ou um banco remoto,
ele falha aqui. A imagem leva uma cópia do repositório; depois de mudar código,
use `docker compose run --rm --build testes`.

Um teste é pulado no container (`tests/test_deploy_dashboard.py`, "git não
instalado"): ele consulta o git, e a imagem não leva nem o git nem a pasta `.git`.

## Imagens

O `Dockerfile` tem três alvos, um por conjunto de dependências:

| Alvo | Dependências | Conteúdo | Serviços |
|---|---|---|---|
| `api` | `requirements-api.txt` | `api/`, `persistence/`, `scraper/`, `scripts/`, `seed/`, migrations | `preparo`, `api` |
| `dashboard` | `requirements-dashboard.txt` | `api/`, `persistence/`, `scraper/`, `dashboard/`, `.streamlit/` | `dashboard` |
| `completa` | `requirements.txt` | o repositório inteiro | `coleta`, `testes` |

Todas rodam com um usuário sem privilégios. Só a `completa` copia o repositório
inteiro, e o `.dockerignore` tira antes o que não pode ir: `.env*` (menos o
`.env.example`), `.neon`, `.streamlit/secrets.toml`, `node_modules/`, e os dados
gerados (`data/`, `output/`, `coleta/`, `*.db`). `tests/test_docker.py` confere
essas regras.

O dashboard usa o mesmo usuário do Postgres local que a API, mas o engine dele
abre toda transação como somente leitura (`dashboard/config.py`). O papel
`dashboard_leitura` de [`deploy.md`](deploy.md) é do banco publicado, não do
compose.
