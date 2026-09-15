# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Python scraper that answers, with real data, which tech area (Backend, Frontend,
Data, Mobile, DevOps, QA, Fullstack, Suporte/Infra, Segurança) hires the most
entry-level developers in Brazil. It collects jobs from seven public portals,
filters to entry-level, classifies each job into a tech area by keyword rules,
dedupes, and exports CSVs/charts/a report. A read-only FastAPI sits on top of
the collected data. Comments, docstrings, and commit messages in this repo are
in Portuguese — follow that convention when editing existing files.

## Commands

```bash
# Run the full scraper (all 7 sources, 13 default search terms)
python main.py

# Common flags
python main.py --sources gupy vagas          # only specific portals
python main.py --terms "estagio dados" "..."  # override search terms
python main.py --max-pages 2 --delay 3        # smaller/slower run
python main.py --strict                       # drop mixed titles like "Júnior/Pleno"
python main.py --all-levels                   # skip seniority filter entirely
python main.py --no-charts                    # skip matplotlib PNG generation
python main.py -v                             # DEBUG logging

# Tests (263 tests, no network — sources are tested against captured real responses)
python -m pytest -q
python -m pytest tests/test_classifier.py -q          # single file
python -m pytest tests/test_classifier.py::test_name  # single test
python -m pytest tests/api -q                          # API tests only (auto-skipped if fastapi isn't installed)

# API (read-only REST over the collected data)
pip install -r requirements.txt
python scripts/import_csv.py            # CSV (newest in output/) -> DATABASE_URL (required) or --db
uvicorn api.app:app --reload            # docs at http://127.0.0.1:8000/docs

# API + Postgres via Docker (handles healthcheck + seed import automatically)
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
  -> export                  (scraper/export.py)       3 CSVs + .md report + charts.py PNGs
```

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
(documented at length in README.md under "Fontes de dados") — read that
section before touching a source file, e.g.:
- Gupy: unofficial public JSON endpoint, `limit` capped at 100, `pagination.total`
  is unreliable so paginate until an empty page instead.
- Vagas.com: server-rendered HTML (no Selenium needed); listing only exposes
  full remote/on-site, not hybrid, in the card.
- ProgramaThor: `?search=` is silently ignored; most listed jobs are expired
  ("Vencida") and must be dropped.
- Trampos.co: consumes an internal SPA JSON API (not officially documented);
  mixes tech and non-tech job categories.
- LinkedIn: guest API, requires numeric `geoId` (not `location=Brasil`, which
  silently returns US jobs); listing has no description, title-only classification.
- Quero Vagas Tech: no text search, lists the entire catalog; the portal's own
  declared seniority is deliberately ignored (deep-dived in README — it mislabels
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

### API (`api/`)

Read-only FastAPI over the same data the scraper produces — no `POST`/`PUT`/`DELETE`
(they respond 405 by design, since writes would just get overwritten by the next
CSV import). `api/vocabulary.py` reads the same `scraper/rules/*.yml` files so
area/technology names stay a single source of truth. `/areas` and `/tecnologias`
are always computed live from the `vagas` table, never read from the pre-aggregated
`ranking_areas.csv`/`skills_por_area.csv` (those are truncated top-N exports).

The database is configured by a single required `DATABASE_URL` (Neon
PostgreSQL), resolved in `scraper/config.py:obter_database_url` with precedence
process env > `.env.local` (written by `neon env pull`) > `.env`. There is no
default database: without it, the API lifespan and the importer raise
`ConfiguracaoError`, whose message never includes the URL. An explicit
destination argument (`make_engine(path)`, `import_csv.py --db`) still wins and
may be a SQLite path — tests rely on this. The engine is lazy
(`api/database.py:get_engine`) so importing the module doesn't require the
variable. `postgres://`/`postgresql://` URLs are rewritten to
`postgresql+psycopg://`. Tests never read the real `.env.local`:
`tests/conftest.py` blanks `ARQUIVOS_ENV` and unsets `DATABASE_URL`. See
`docs/neon-setup.md`; `.neon`, `.env*` (except `.env.example`) and
`node_modules/` are git-ignored and must stay that way.

Import (`scripts/import_csv.py`) is idempotent — job identity is `(source,
external_id)`, so re-running updates rather than duplicates. `skills` (a CSV
string column) is normalized into a `tecnologias` table + many-to-many
association on import.

Deploy (`render.yaml`, Render free tier): the scraper never runs on the server
(cloud IPs get blocked by job portals); the DB is rebuilt from the committed
`seed/vagas.csv` snapshot on every boot since the disk is ephemeral. Build uses
`requirements-api.txt` (no matplotlib — the API's import graph never touches
`scraper/charts.py`). To publish new data: run the scraper locally, commit an
updated `seed/vagas.csv`, and update `--referencia` in `render.yaml`.

### Tests

`tests/` needs no network — sources are tested against real captured responses
fixtures (mainly in `test_sources.py`). `tests/api/` is a separate subtree
guarded by `pytest.importorskip("fastapi")` so `pytest tests/` still works for
someone who only installed the scraper deps. API tests use an in-memory SQLite
(`StaticPool` to keep one connection alive) with `app.dependency_overrides[get_db]`,
never the real `data/vagas.db`.
