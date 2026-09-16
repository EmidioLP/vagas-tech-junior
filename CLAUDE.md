# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Python scraper that answers, with real data, which tech area (Backend, Frontend,
Data, Mobile, DevOps, QA, Fullstack, Suporte/Infra, Segurança) hires the most
entry-level developers in Brazil. It collects jobs from public portals (six by default, seven registered),
filters to entry-level, classifies each job into a tech area by keyword rules,
dedupes, and writes a history to PostgreSQL (Neon) on a GitHub Actions schedule;
CSVs/charts/a report are optional. A read-only FastAPI and a read-only Streamlit
dashboard sit on top of the collected data. Comments, docstrings, and commit messages in this repo are
in Portuguese — follow that convention when editing existing files.

## Docs map

Documentation is in Portuguese. Entry point: `docs/architecture.md` (Mermaid flow
of portals → Actions → pipeline → Neon → API/dashboard, one sentence per component,
repo tree and a table of every doc). When editing docs:
- `docs/decisoes/` holds short ADRs (context, decision, consequences with cost,
  what would change it): Neon branches, `jobs` + hash snapshots, Actions instead of
  Airflow, no medallion/dbt, Render + Streamlit Cloud, quality checks in Python. A new
  structural decision, or reversing one, is a new ADR (mark the old one superseded,
  don't delete it).
- Moved out of the README in stage 13: `docs/fontes.md` (per-portal details,
  server etiquette, adding a portal), `docs/classificacao.md` (tech gate, area,
  modality, skills, charts, editing rules), `docs/api.md` (endpoints, Docker,
  `DATABASE_URL`, dates, API deploy), `docs/limitacoes.md` (ethical/technical
  limits, blocked sources, frequency, source bias, rule changes over history).
- `docs/baseline.md` and `docs/resultados-2026-09-15.md` are dated records; don't
  update them to match the current state. `docs/resultados-2026-09-15.md` links to
  the README anchors `#como-esses-números-foram-apurados` and
  `#limitações-honestas`, so keep those headings.
- Only `tests/test_deploy_dashboard.py` pins doc content (`docs/deploy.md`).

## Commands

```bash
# Run the full scraper (the 6 default sources, 13 default search terms) and write to the DB.
# Needs DATABASE_URL + `alembic upgrade head`; checked BEFORE collecting.
python main.py

# Common flags
python main.py --csv                          # also export CSVs + .md report + charts
python main.py --no-db --csv                  # files only, no database
python main.py --db data/teste.db             # other DB (URL or SQLite path), beats DATABASE_URL
python main.py --sources gupy vagas          # only specific portals
python main.py --terms "estagio dados" "..."  # override search terms
python main.py --max-pages 2 --delay 3        # smaller/slower run
python main.py --strict                       # drop mixed titles like "Júnior/Pleno"
python main.py --all-levels                   # skip seniority filter entirely
python main.py --csv --no-charts              # skip matplotlib PNG generation
python main.py -v                             # DEBUG logging
python main.py --resumo coleta/resumo.md      # also write a non-sensitive Markdown summary (used by collect.yml)
python main.py --respect-interval             # skip (recorded) if COLLECTION_INTERVAL_DAYS hasn't passed since the last full run

# Tests (no network — sources are tested against captured real responses)
python -m pytest -q
python -m pytest tests/test_classifier.py -q          # single file
python -m pytest tests/test_classifier.py::test_name  # single test
python -m pytest tests/api -q                          # API tests only (auto-skipped if fastapi isn't installed)

# Dashboard (read-only Streamlit over jobs/job_snapshots/collection_runs; DATABASE_URL, or DASHBOARD_DB to override)
streamlit run dashboard/app.py
python -m pytest tests/dashboard -q

# API (read-only REST over the collected data)
pip install -r requirements.txt
uvicorn api.app:app --reload            # docs at http://127.0.0.1:8000/docs (reads jobs/job_snapshots)
python scripts/carregar_seed.py         # seed/vagas.csv -> history of a LOCAL migrated DB (refuses DBs with collection_runs)

# Migrations (Alembic; URL comes from scraper/config.py, never alembic.ini)
alembic upgrade head --sql              # review SQL without connecting
alembic upgrade head                    # apply (uses DATABASE_URL_UNPOOLED when present)
alembic revision --autogenerate -m "..."  # then review by hand, see docs/migrations.md
python -m pytest tests/api/test_migrations.py -q

# API + Postgres via Docker (healthcheck, alembic upgrade head and seed load automatically)
docker compose up --build
docker compose down          # add -v to also drop the db volume
```

There is no lint/format tooling configured in this repo (no ruff/black/mypy config) — don't invent one.

## Architecture

### Pipeline (`scraper/pipeline.py`)

```
collect (per source, per search term)
  -> seniority filter        (scraper/seniority.py)   keep júnior/estágio/trainee/aprendiz
  -> deduplicate             (scraper/dedupe.py)       by source+id, then title+company
  -> tech relevance gate     (scraper/classifier.py)   drop "Analista Contábil Jr" etc.
  -> area classification     (scraper/classifier.py)   weighted keyword scoring
  -> skill extraction        (scraper/skills.py)       must run BEFORE export truncates description
  -> persist                 (persistence/)            jobs + job_snapshots, idempotent (default on)
  -> export                  (scraper/export.py)       3 CSVs + .md report + charts.py PNGs (only with --csv)
```

The database is the source of truth; CSV export is optional and never a
prerequisite for persisting. `pipeline.preparar_banco` validates the DB
(URL, connectivity, current schema) before `collect` so a bad config doesn't
waste a multi-minute scrape. One `collected_at` (UTC) per run.

Execution policy lives in `scraper/execucao.py` (pure) and every DB run is
recorded in `collection_runs` (`persistence/execucoes.py`), skips included:
- `--respect-interval` needs `COLLECTION_INTERVAL_DAYS` (no default) and skips
  unless X days (compared by UTC date) passed since the last run with
  `full_scope` (all `DEFAULT_SOURCES`, default terms, ≥5 pages) and status
  `success`/`partial`.
- With X known (always under the guard; forced runs if the env var is set),
  `calcular_agenda` fills `result.agenda`, printed/summarized as `Última coleta:
  dia DD/MM/AAAA e próxima: dia DD/MM/AAAA` and stored in `next_run_on`: next =
  last full run + X, or tomorrow if that date passed. The project uses X=2
  (GitHub Repository Variable).
- `PoliteSession.failed_count` counts requests that gave up (sources only stop
  paginating on `None`), so a blocked portal shows as `failed`, not "0 jobs".
- `collect` isolates whole-source exceptions. Run status: `failed` (exit 1) if
  all sources failed or no jobs; `partial` (exit 0, or 1 with job write
  failures or a high quality alert) if any source isn't `ok`; else `success`.
- Quality checks (`scraper/qualidade.py`, pure; `docs/data-quality.md`) run in
  `_aplicar_politica`, after persisting and **before** closing absent jobs. They
  never fix or delete data. High alerts (`fonte_zerada`: default source with 0 raw
  jobs and no failed request; `queda_brusca`: < 30% of the median of previous full
  runs, needs ≥3 runs and median ≥30; out-of-domain area/modalidade; essential
  field empty above a per-source limit) turn an `ok` source into `partial` (so it
  doesn't close jobs) and force exit 1; low alerts only show up. Empty-field limits
  have per-source exemptions (LinkedIn has no description, etc.): never a global
  not-null. History comes from `persistence/execucoes.historico_vagas_brutas`
  (skips failed/zero days). Alerts go to `summary.qualidade` (counts only, no URL)
  and to the `--resumo` Qualidade section. `tests/test_qualidade.py` pins that the
  15/09 seed collection yields no alerts; recalibrate constants with data.
- Freshness (`persistence/frescor.py`, read by API and dashboard; lives in
  `persistence/` because the dashboard can't import `scraper.execucao`): X comes
  from the latest `collection_runs.interval_days` (not the env var, which only
  exists in Actions). States: `sem_coleta`, `sem_intervalo` (no ruler), `vencido`
  (last full success/partial > 2×X UTC days), `coleta_parada` (no run of any
  status for > 2 days: the daily cron records even skips), `em_dia`. `/health`
  stays liveness and always 200 (Render's `healthCheckPath`); `GET /health/dados`
  answers 503 for `vencido`/`coleta_parada`/`sem_coleta`/DB down (error type
  only). The dashboard Overview shows a `st.warning` for `vencido`/`coleta_parada`.
- Correlation: `main.py` passes `GITHUB_RUN_ID` (digits only) as `id_externo`;
  it goes to the log, `summary.github_run_id` and the resumo, together with the
  `collection_runs.id` (`meta["execucao_id"]`). Playbook: `docs/observability.md`.

`main.py` only builds a `Settings` (scraper/config.py) and calls `pipeline.run()`.
`Settings` and the YAML rule files below are the two places to change behavior
without touching the pipeline itself.

### Sources (`scraper/sources/`)

Every portal is a class inheriting `JobSource` (`base.py`), implementing
`fetch_term(term) -> list[Job]`, registered in `sources/__init__.py`'s
`SOURCE_REGISTRY`. `JobSource.fetch()` isolates failures per-term so one bad
portal/term never aborts the whole run. Adding a new source is: one new file +
one registry line, and it automatically gets seniority filtering, dedup,
classification, and export for free.

Each source has non-obvious integration details discovered by live testing
(documented at length in `docs/fontes.md`) — read that doc before touching a
source file, e.g.:
- Gupy: unofficial public JSON endpoint, `limit` capped at 100, `pagination.total`
  is unreliable so paginate until an empty page instead.
- Vagas.com: server-rendered HTML (no Selenium needed); listing only exposes
  full remote/on-site, not hybrid, in the card.
- ProgramaThor: `?search=` is silently ignored; most listed jobs are expired
  ("Vencida") and must be dropped. Excluded from the default collection
  (`FORA_DA_COLETA_PADRAO` / `DEFAULT_SOURCES` in `sources/__init__.py`) because it
  returns HTTP 403 to cloud IPs; still registered, so `--sources programathor`
  and the API's `source` filter keep working.
- Trampos.co: consumes an internal SPA JSON API (not officially documented);
  mixes tech and non-tech job categories.
- LinkedIn: guest API, requires numeric `geoId` (not `location=Brasil`, which
  silently returns US jobs); listing has no description, title-only classification.
- Quero Vagas Tech: no text search, lists the entire catalog; the portal's own
  declared seniority is deliberately ignored (deep-dived in `docs/fontes.md` — it mislabels
  managers as "Intern").
- GeekHunter: `robots.txt` disallows `/api/` and `/feeds/`, so it's collected via
  sitemap -> per-job HTML page with structured `JobPosting` data, not an API call.

Catho and Indeed BR are evaluated and deliberately excluded (hard-blocked by the
portals) — no simulated data is ever substituted for a blocked source.

### Classification rules (`scraper/rules/*.yml`)

Business logic lives in three commented YAML files, editable without touching
Python:
- `areas.yml` — per-area keywords at two weight tiers (`peso_alto`=4.0,
  `peso_medio`=1.0), plus `tech_gate` (title/description signals + exclusions)
  that decides if a listing is even a tech job before it's scored.
- `seniority.yml` — what counts as entry-level vs. above.
- `skills.yml` — technologies/tools searched for and their aliases.

Key scoring rules in `classifier.py`: a title match counts 3x a description
match (`title_boost`); if any area matched in the title, only title-matched
areas compete ("título dominante"); jobs scoring below `min_score` (3.0) fall
into "Outros/TI Geral" rather than being force-assigned. Keywords match as
whole words/phrases over normalized text (lowercased, accents stripped) to
avoid substring false positives (e.g. "go" inside "Goiânia").

Two documented traps when editing `areas.yml`: don't use bare `data` for the
Data area (matches "data de admissão" in Portuguese), and don't use bare
`seguranca` for Segurança (matches "normas de segurança" boilerplate in almost
any support job listing — inflated that area 4x -> 45 in an early run).

### Dashboard (`dashboard/`)

Read-only Streamlit app; it never collects, transforms or writes. All DB access
goes through `dashboard/consultas.py` (pure functions taking an engine; SQLAlchemy
errors become `DadosIndisponiveis` carrying only the error type). `config.py`
builds a read-only engine (`postgresql_readonly` per transaction, which works
behind Neon's pooler; `PRAGMA query_only` on SQLite) from `DATABASE_URL`, or
`DASHBOARD_DB` if set. "Last collection" uses the interval guard's rule (full
scope, `success`/`partial`), "active jobs" is `jobs.is_active`. `app.py` caches
the engine (`st.cache_resource`) and every query (`st.cache_data`, 10 min TTL,
keyed by the frozen `Filtros` dataclass) and hands pages a `paginas.Dados` of
callables, so pages never see the engine.

Analytics semantics (keep them straight; the UI labels depend on it): every
"vagas" count is unique `jobs`, never snapshot rows. Snapshots are written only
when `content_hash` changes, so snapshots per day = state changes, not jobs seen.
Overview/Tecnologias are the current photo (active jobs + latest snapshot via
`max(collected_at)` join; period doesn't apply). Histórico reconstructs each UTC
collection day in Python (`serie_historica`): open = `first_seen_at` before day
end and not `closed_at` by then, area/modalidade from the snapshot in force at
day end. Vagas lists jobs *seen* in the period, links only via `url_segura`
(http/https). Tecnologias hides the overall ranking below `BASE_MINIMA_TECNOLOGIAS`
(30; base = active jobs citing any technology); the per-area panels
(`tecnologias_por_area`, each area with its own base, 0–100% axis) hide areas
below `BASE_MINIMA_POR_AREA` (15) and mark 15–29 as indicative. Filters are always bind params. The data
layer must not import FastAPI, requests, bs4 or yaml (`requirements-dashboard.txt`
omits them; a test checks it). `banco_historico` lives in `tests/conftest.py`; the
known analytics scenario is `tests/cenario_historico.py` (shared with the API
equivalence test).

Deploy (`docs/deploy.md`, Streamlit Community Cloud, manual via the web panel):
entrypoint `dashboard/app.py`, deps `dashboard/requirements.txt` (just
`-r ../requirements-dashboard.txt`, since the platform looks in the entrypoint's
folder first). `DATABASE_URL` is a root-level secret, which Streamlit exports as
an env var at server start, so the code never uses `st.secrets`. It points at
`dados-main` with the SQL-created `dashboard_leitura` role (SELECT on the 5 tables
the dashboard reads + `default_transaction_read_only`); a new table read by the
dashboard needs a new GRANT. `tests/test_deploy_dashboard.py` pins this.

The README keeps only purpose, published links, dated "Principais achados"
(interpretation), a secret-free quickstart and a limitations summary; it links to
the dashboard for current numbers, and full tables/charts of a collection live in
a dated report (`docs/resultados-2026-09-15.md`). Don't put live-looking numbers
back in the README, and put long technical detail in `docs/` (see "Docs map").

### API (`api/`)

Read-only FastAPI over the history the pipeline writes — no `POST`/`PUT`/`DELETE`
(they respond 405 by design, since writes would just get overwritten by the next
collection). `api/vocabulary.py` reads the same `scraper/rules/*.yml` files so
area/technology names stay a single source of truth.

The API and the dashboard share one "current photo" rule:
`persistence/foto_atual.py:vagas_atuais()` (each `jobs` row joined to its latest
snapshot; SQL only, no FastAPI/Streamlit/yaml imports). `api/crud.py` builds on it:
`/vagas` lists active jobs unless `incluir_encerradas=true`, `/vagas/{id}` is
`jobs.id` (closed jobs included), `/areas` and `/tecnologias` count active jobs by
the latest snapshot, computed live, never read from the pre-aggregated
`ranking_areas.csv`/`skills_por_area.csv`. `tests/api/test_api_equivalencia_dashboard.py`
pins API == dashboard numbers on the same DB. API test data is built in the history
model (`tests/api/historico_api.py` builders + `seed` fixture).

The database is configured by a single required `DATABASE_URL` (Neon
PostgreSQL), resolved in `scraper/config.py:obter_database_url` with precedence
process env > `.env.local` (written by `neon env pull`) > `.env`. There is no
default database: without it, the API lifespan, the pipeline and the seed loader raise
`ConfiguracaoError`, whose message never includes the URL. An explicit
destination argument (`make_engine(path)`, `carregar_seed.py --db`) still wins and
may be a SQLite path — tests rely on this. The engine is lazy
(`api/database.py:get_engine`) so importing the module doesn't require the
variable. `postgres://`/`postgresql://` URLs are rewritten to
`postgresql+psycopg://`. Tests never read the real `.env.local`:
`tests/conftest.py` blanks `ARQUIVOS_ENV` and unsets `DATABASE_URL`. See
`docs/neon-setup.md`; `.neon`, `.env*` (except `.env.example`) and
`node_modules/` are git-ignored and must stay that way.

History tables live in the same metadata: `jobs` (ORM `JobRecord` — identity and
lifecycle only, unique `(source, external_id)`) and `job_snapshots` (ORM
`JobSnapshot` — per-collection observed state, unique `(job_id, collected_at)`,
FK `RESTRICT` so history can't be deleted silently), plus
`job_snapshot_tecnologias`. The ORM name `JobRecord` exists to avoid clashing
with the scraper dataclass `scraper.models.Job`. The pipeline writes them
through `persistence/`, and the API and dashboard read them. Every model change needs an Alembic
migration: `tests/api/test_migrations.py` runs `alembic check`. See
`docs/data-model.md`.

### Persistence (`persistence/`)

SQL lives only here, never in sources or the pipeline; the pipeline imports it
lazily, so `--no-db` works without SQLAlchemy. `repositorio.persistir_vagas`:
- upserts `jobs` by `(source, external_id)` with dialect `INSERT ... ON CONFLICT`
  (postgresql/sqlite) — the DB constraint, not in-memory dedupe, guarantees
  integrity. `last_seen_at` never moves back, `first_seen_at` never forward,
  seen jobs get `is_active=true`; the upsert never deactivates (it clears `missing_since`
  and reopens closed jobs). `encerrar_ausentes` closes jobs
  (`is_active=false`, `closed_at`) missing from the raw listing in two
  consecutive trusted runs on different UTC days (full scope, source `ok` with
  ≥1 listed job); the first absence only sets `missing_since`. Nothing is
  deleted.
- writes a snapshot only if `content_hash` differs from the previous snapshot
  and there's none for this job at this `collected_at`. The hash
  (`assinatura.py`, v1, pinned by `tests/test_assinatura.py`) covers exactly the
  stored snapshot fields + sorted tecnologias; not `url`/`search_term`. Changing
  it means bumping `VERSAO`, which re-snapshots every job.
- one transaction per source + SAVEPOINT per job: data errors
  (`IntegrityError`/`DataError`/`ValueError`) undo only that job and count as
  failures; any other DB error undoes the whole source. Committed sources are
  never affected. `make_engine` applies the pysqlite SAVEPOINT workaround for SQLite.
- returns `ResumoPersistencia` (created/updated jobs, snapshots created/skipped,
  failures, per source); `main.py` prints it and exits 1 on failures, 2 on
  `ConfiguracaoError`.

The legacy CSV flow is gone: `vagas`/`vaga_tecnologia` were dropped by migration
`85084f63871c` (its downgrade recreates them empty, never the data) and
`import_csv.py` was removed. `scripts/carregar_seed.py` loads an exported CSV
(default `seed/vagas.csv`) into the history through `persistir_vagas`, as a
collection on a fixed day (`DATA_DO_SEED`, so relative dates are stable; bump it
with the CSV). It's idempotent and refuses any DB with rows in `collection_runs`
(it would write fake past snapshots into real history). Docker Compose runs
`alembic upgrade head && carregar_seed.py && uvicorn`, so the image copies
`alembic.ini`, `migrations/`, `persistence/`, `scripts/` and `seed/`, and
`requirements-api.txt` includes alembic.

Deploy (`render.yaml`, Render free tier): the API reads the Neon branch
`dados-main`; `DATABASE_URL` is declared with `sync: false` (value only in the
Render dashboard) and `startCommand` is just `uvicorn` — no seed load and no migrations
on boot (the DB persists; doing either on every free-tier wake would take
minutes; migrations on `dados-main` are applied by hand, `docs/neon-setup.md`). The API serves what the scheduled collection writes to `dados-main`. `tests/test_render_yaml.py` pins
this. Neon branches: `production` untouched, `feature-data-platform` for local
dev, `dados-main` for main/Render/Actions. Build uses `requirements-api.txt` (no
matplotlib — the API's import graph never touches `scraper/charts.py`).
`external_id` is `VARCHAR(100)` (GeekHunter ids are 64-char hashes; ids are never
truncated). Rollback: `docs/rollback-merge.md`.

### Tests

`tests/` needs no network — sources are tested against real captured responses
fixtures (mainly in `test_sources.py`). `tests/api/` is a separate subtree
guarded by `pytest.importorskip("fastapi")` so `pytest tests/` still works for
someone who only installed the scraper deps. API tests use an in-memory SQLite
(`StaticPool` to keep one connection alive) with `app.dependency_overrides[get_db]`,
never a real database. Persistence tests use the `banco_historico`
fixture (`tests/api/conftest.py`): a temp SQLite file built by `alembic upgrade
head`, so they test the migration schema. The pipeline integration test
(`tests/api/test_pipeline_persistencia.py`) monkeypatches `pipeline.collect`
instead of hitting the network.

### GitHub Actions (`.github/workflows/`)

`ci.yml` runs `python -m pytest -q` on push/PR (Python 3.11 + 3.13) with no
secrets. `collect.yml` has a daily `schedule` (09:00 UTC, only wakes it up) plus
`workflow_dispatch`: scheduled runs pass `--trigger schedule --respect-interval`
with `COLLECTION_INTERVAL_DAYS` from `vars` (a Repository Variable); manual runs
force the collection unless `respeitar_intervalo=true`. It runs
`python main.py ... --resumo coleta/resumo.md` with `DATABASE_URL` from Secrets,
never runs migrations or `-v`, and on failure uploads only the log passed through
`scripts/sanitizar_log.py`. `tests/test_workflows.py` pins these rules. See
`docs/automation.md`.
