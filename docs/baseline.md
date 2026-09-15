# Linha de base — estado do projeto em 15/09/2026

Retrato do `vagas-tech-junior` antes da evolução para plataforma de dados
(ver `docs/roadmap-status.md`). Serve para responder: *o que funciona hoje e
como provar que continuou funcionando?* Nenhum código de produção foi alterado
para produzir este documento.

- **Branch de trabalho:** `feature/data-platform`, criada a partir de `main` em
  `f01e8ff` ("Atualiza os resultados com a coleta de 15/09/2026").
- **Árvore no início:** limpa, exceto `.llm/` (prompts do roadmap) e `CLAUDE.md`,
  ambos não rastreados. Nada foi descartado.

---

## 1. Arquitetura e fluxo de dados

Dois blocos independentes, ligados apenas por um **arquivo CSV**:

```
                        SCRAPER (roda só na máquina local)
main.py ─► Settings (scraper/config.py) ─► pipeline.run() (scraper/pipeline.py)
   │
   ├─ collect          7 fontes × termos, PoliteSession (delay, retry, UA)
   ├─ senioridade      scraper/seniority.py   + rules/seniority.yml
   ├─ deduplicação     scraper/dedupe.py      (source:external_id, depois título+empresa)
   ├─ portão tech      scraper/classifier.py  + rules/areas.yml (tech_gate)
   ├─ classificação    scraper/classifier.py  + rules/areas.yml
   ├─ skills           scraper/skills.py      + rules/skills.yml
   └─ export           scraper/export.py, scraper/charts.py
            │
            ▼
   output/vagas_<ts>.csv  (+ ranking_areas, skills_por_area, relatorio .md, 3 PNG)
            │   cópia manual e commit
            ▼
   seed/vagas.csv  (snapshot versionado, 597 vagas)
            │
            ▼                     API (local, Docker ou Render)
   scripts/import_csv.py ─► SQLite ou PostgreSQL ─► api/app.py (FastAPI, só leitura)
                            (api/database.py,        /vagas, /areas, /tecnologias,
                             api/models.py)          /health
```

- **Não há persistência direta do pipeline em banco.** O pipeline só grava
  arquivos; o banco é um espelho do CSV, preenchido pelo importador.
- **Não há histórico.** Reimportar atualiza a linha existente; uma vaga que some
  do portal continua no banco até um `--recriar`.
- **Não há migrations.** O schema é criado com `Base.metadata.create_all` no
  lifespan da API (`init_db()`) e no importador.

## 2. Fontes

Registradas em `scraper/sources/__init__.py` (`SOURCE_REGISTRY`). Cada uma herda
`JobSource` (`scraper/sources/base.py`) e implementa `fetch_term(term)`; falha
num termo é registrada em `SourceStats.errors` e não derruba a coleta.

| Nome (`--sources`) | Portal | Acesso |
|---|---|---|
| `gupy` | Gupy | JSON público do portal (`limit` ≤ 100) |
| `vagas` | Vagas.com.br | HTML renderizado no servidor |
| `programathor` | ProgramaThor | HTML; filtra por `expertise`, descarta vencidas |
| `trampos` | Trampos.co | JSON da SPA (`tr` = busca) |
| `linkedin` | LinkedIn Jobs | API de convidado, `geoId=106057199`, sem descrição |
| `querovagastech` | Quero Vagas Tech | JSON público; lista o acervo inteiro |
| `geekhunter` | GeekHunter | sitemap → HTML com `JobPosting` (robots proíbe `/api/`) |

Catho (HTTP 404 "Operação Inválida") e Indeed BR (desafio Cloudflare) foram
avaliadas e ficaram de fora. Nenhum dado é simulado. Detalhes por fonte no
`README.md`, seção "Fontes de dados".

Coleta de referência (15/09/2026): 1.597 brutas → 1.254 após senioridade →
911 após dedupe → **597** após o portão de tecnologia.

## 3. Comandos

| Comando | Para quê | Nesta etapa |
|---|---|---|
| `python -m pytest -q` | Suíte completa | **Executado** |
| `python -m pytest tests/api -q` | Só a API | **Executado** |
| `python -m pytest --collect-only -q` | Contagem de testes | **Executado** |
| `python main.py [--sources …] [--terms …] [--max-pages N]` | Coleta real | Não executado (acessa portais) |
| `python scripts/import_csv.py [--csv …] [--db …] [--recriar] [--referencia AAAA-MM-DD]` | CSV → banco | Não executado |
| `uvicorn api.app:app --reload` | API local | Não executado |
| `docker compose up --build` | API + Postgres 16 | Não executado |

Não existe ferramenta de lint/formatação configurada, `pyproject.toml` nem CI
(`.github/` não existe).

## 4. Resultado dos testes

Ambiente: Windows 11, Python 3.13.9 (anaconda, sem venv), pytest 8.4.2,
FastAPI 0.141.1, SQLAlchemy 2.0.43, psycopg 3.3.4.

```
$ python -m pytest -q -rs
263 passed, 1 warning in 3.23s

$ python -m pytest tests/api -q
74 passed, 1 warning in 1.39s
```

- **263 aprovados, 0 falhas, 0 pulados.** Bate com os 263 citados no README.
- 189 testes do scraper (`tests/`) e 74 da API (`tests/api/`).
- Nenhum teste usa rede: os parsers rodam contra respostas reais capturadas;
  a API usa SQLite em memória com `app.dependency_overrides[get_db]`.
- `tests/api/conftest.py` faz `pytest.importorskip("fastapi")`: sem FastAPI,
  esses 74 são pulados em vez de falhar.
- Único aviso: `StarletteDeprecationWarning` — `starlette.testclient` com
  `httpx` está depreciado em favor de `httpx2`. Não afeta resultado; é
  dependência de ambiente, não do código.

## 5. Dependências

| Arquivo | Uso | Diferenças relevantes |
|---|---|---|
| `requirements.txt` | Desenvolvimento local (tudo) | Tem matplotlib, pytest, httpx. **Não tem psycopg** — Postgres local só funciona se o driver for instalado à parte. |
| `requirements-api.txt` | Docker e Render | Tem `psycopg[binary]`; **sem matplotlib** (a API nunca importa `scraper/charts.py`). Inclui requests/bs4/PyYAML porque `api.vocabulary` importa `scraper.sources`. |

Versões de Python divergem: **3.11** no `Dockerfile` e no `render.yaml`,
**3.13** no ambiente local onde a suíte rodou.

## 6. Pontos de acoplamento CSV → banco → API

- **Contrato do CSV:** `JOB_COLUMNS` em `scraper/export.py`, gerado por
  `Job.to_row()` (`scraper/models.py`). `description` é truncada em 500
  caracteres e `skills` vira a string `"A, B, C"`. Renomear coluna quebra o
  importador em silêncio (`linha.get()` devolve vazio).
- **Identidade da vaga:** `(source, external_id)`, `UNIQUE` em
  `api/models.py`. É o que torna a importação idempotente. O `id` inteiro é
  só a chave da URL `/vagas/{id}`.
- **Tecnologias:** a string `skills` é normalizada em `tecnologias` +
  `vaga_tecnologia` (M:N). Nomes que não estão em `rules/skills.yml` são
  **descartados** na importação.
- **Vocabulário único:** `api/vocabulary.py` lê `rules/areas.yml`,
  `rules/skills.yml`, `WORKPLACE_ORDER` e `AVAILABLE_SOURCES` para gerar os
  enums de validação (422). Mudar YAML ou registro de fontes muda a API.
- **Datas:** o CSV mistura ISO, `dd/mm/aaaa` e relativas ("Ontem"). Relativas
  são resolvidas contra `--referencia` ou o timestamp do nome do arquivo
  (`api/dates.py`). Seed e deploy fixam `--referencia 2026-09-15`.
- **Seleção do banco:** `database_url()` em `api/database.py` — argumento >
  `DATABASE_URL` > `VAGAS_DB` > `data/vagas.db`. `postgres://` e
  `postgresql://` viram `postgresql+psycopg://`. Sem variável, **SQLite**.
- **`engine` global:** `api/database.py` cria o engine no import do módulo.
- **Deploy:** Render roda `import_csv.py --csv seed/vagas.csv --recriar` a cada
  boot (disco efêmero); o compose importa o seed sem `--recriar` sobre um
  volume Postgres. O scraper nunca roda em servidor.

## 7. Configuração e segredos

- Não havia `.env` nem `.env.example`. Criado `.env.example` só com
  `DATABASE_URL` e `VAGAS_DB` comentados e valores fictícios.
- O `.gitignore` tinha `.env.*`, que também ignorava `.env.example`; foi
  adicionada a exceção `!.env.example`.
- **Nenhum segredo encontrado** no código nem no histórico git (busca por
  senhas, tokens, webhooks e URLs com credenciais). Ocorrências são apenas:
  - `vagas/vagas` no `docker-compose.yml` — credencial de desenvolvimento do
    Postgres local, aceitável ali, mas não deve ser reaproveitada em ambiente
    remoto;
  - URLs fictícias (`u:p@`, `vagas:segredo@`) em `tests/api/test_database_url.py`.

## 8. Riscos e pontos afetados nas próximas etapas

| Etapa | Ponto hoje | Impacto |
|---|---|---|
| 01 Neon | `DATABASE_URL` é opcional; o default SQLite sustenta Render, `uvicorn` local e os testes. | Exigir a variável quebra esses três caminhos se não houver tratamento explícito. |
| 02 Alembic | `create_all` em `init_db()` (lifespan) e em `import_csv.py`; `--recriar` faz `drop_all`. | Os dois precisam passar a respeitar migrations. |
| 03/04 Snapshots e persistência | Pipeline só grava CSV; import sobrescreve a linha. | Não existe dado histórico para migrar — o histórico começa do zero. Contrato do CSV (§6) é a fronteira a preservar. |
| 05 CI | Não há workflow. Python 3.11 no deploy vs 3.13 local. | Suíte validada só em 3.13. |
| 06 Intervalo/resiliência | Falhas por termo já são isoladas em `JobSource.fetch()`. | Reaproveitar em vez de reescrever. |
| 12 API analítica | Agregações de `/areas` e `/tecnologias` são calculadas da tabela `vagas`. | Endpoints atuais não devem mudar de formato. |
| 15 Deploy | Render serve snapshot em SQLite reconstruído a cada boot. | Migrar para Neon muda o modelo de deploy. |

Outros pontos observados, **não corrigidos** nesta etapa:

- Documentação desatualizada: a `DESCRIPTION` em `api/app.py` e a seção
  "Como rodar" do README dizem que os dados vêm só da Gupy e do Vagas.com,
  mas são sete fontes.
- `requirements.txt` não inclui `psycopg`, então `DATABASE_URL` Postgres falha
  localmente numa instalação limpa.
- Bytecode órfão, sem `.py` correspondente e sem nenhum registro no git:
  `scraper/__pycache__/notificacao*.pyc`, `scripts/__pycache__/avisar_discord*.pyc`,
  `tests/__pycache__/test_notificacao*.pyc`. Indica trabalho local de notificação
  (Discord) que não foi versionado. Não interfere na suíte (263 coletados, sem
  esses módulos).
- Arquivos locais ignorados pelo git: `data/vagas.db`, `data/render_sim.db`,
  `output/` da coleta de 15/09/2026.
