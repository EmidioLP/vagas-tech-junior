"""Carrega um CSV exportado pelo scraper no historico (`jobs` + `job_snapshots`).

    python scripts/carregar_seed.py                       # seed/vagas.csv em DATABASE_URL
    python scripts/carregar_seed.py --db data/local.db    # SQLite ja migrado
    python scripts/carregar_seed.py --csv output/vagas_20260915_101500.csv --coletado-em 2026-09-15

Serve para ter dados sem rede num banco **local**: e o que o Docker Compose roda
depois de `alembic upgrade head`. Grava pela mesma persistencia do pipeline
(`persistence.repositorio.persistir_vagas`), como se o CSV fosse uma coleta feita
em `--coletado-em`. Rodar de novo e seguro: nao cria vagas nem snapshots.

**Nunca num banco com coletas reais.** Se `collection_runs` tiver alguma linha, o
script recusa: o CSV viraria snapshots falsos no passado do historico (a
`dados-main`, por exemplo).
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from datetime import date, datetime, time, timezone
from pathlib import Path

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.database import make_engine  # noqa: E402
from api.models import CollectionRun  # noqa: E402
from persistence.repositorio import persistir_vagas  # noqa: E402
from scraper.config import PROJECT_ROOT, ConfiguracaoError  # noqa: E402
from scraper.models import Job  # noqa: E402

logger = logging.getLogger("carregar_seed")

SEED = PROJECT_ROOT / "seed" / "vagas.csv"
# Dia da coleta que gerou seed/vagas.csv. Atualize junto com o arquivo.
DATA_DO_SEED = date(2026, 9, 15)
# Meio-dia UTC: o dia continua o mesmo no fuso do Brasil, que a persistencia usa
# para resolver datas relativas ("Ontem").
HORA_DA_COLETA = time(12, 0, tzinfo=timezone.utc)

CAMPOS_TEXTO = (
    "company", "url", "description", "location", "workplace_type",
    "published_date", "search_term", "area", "area_matches", "seniority",
)


class CargaRecusada(RuntimeError):
    """Banco sem schema ou com coletas reais."""


def _data_iso(valor: str) -> date:
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Data inválida: {valor!r}. Use o formato AAAA-MM-DD."
        ) from None


def _float(valor: str | None) -> float:
    try:
        return float(valor) if valor not in (None, "") else 0.0
    except ValueError:
        return 0.0


def ler_vagas(csv_path: Path) -> list[Job]:
    """Linhas do CSV como `Job`. Linha sem fonte, id ou titulo e ignorada."""
    vagas = []
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        for linha in csv.DictReader(fh):
            identidade = {c: (linha.get(c) or "").strip() for c in ("source", "external_id", "title")}
            if not all(identidade.values()):
                continue
            vagas.append(Job(
                **identidade,
                **{c: (linha.get(c) or "").strip() for c in CAMPOS_TEXTO},
                area_score=_float(linha.get("area_score")),
                skills=[n.strip() for n in (linha.get("skills") or "").split(",") if n.strip()],
            ))
    return vagas


def _verificar_destino(engine) -> None:
    if not inspect(engine).has_table("jobs"):
        raise CargaRecusada(
            "O banco não tem o schema do histórico. Rode `alembic upgrade head` antes."
        )
    with Session(engine) as db:
        coletas = db.scalar(select(func.count()).select_from(CollectionRun)) or 0
    if coletas:
        raise CargaRecusada(
            f"O banco já tem {coletas} execução(ões) em collection_runs. A carga do "
            "seed é só para bancos locais sem coletas reais."
        )


def carregar(csv_path: Path, destino: str | Path | None = None,
             coletado_em: date = DATA_DO_SEED):
    """Grava o CSV no historico. Devolve o `ResumoPersistencia`."""
    engine = make_engine(destino)
    try:
        _verificar_destino(engine)
        vagas = ler_vagas(csv_path)
        collected_at = datetime.combine(coletado_em, HORA_DA_COLETA)
        return persistir_vagas(vagas, engine, collected_at)
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Carrega um CSV do scraper no histórico de um banco local.",
    )
    parser.add_argument("--csv", type=Path, default=SEED,
                        help="CSV a carregar (padrão: seed/vagas.csv).")
    parser.add_argument(
        "--db", default=None, metavar="DESTINO",
        help="Caminho de arquivo SQLite ou URL PostgreSQL. Padrão: DATABASE_URL.",
    )
    parser.add_argument(
        "--coletado-em", type=_data_iso, default=DATA_DO_SEED, metavar="AAAA-MM-DD",
        help=f"Dia da coleta que gerou o CSV (padrão: {DATA_DO_SEED:%Y-%m-%d}, o do seed).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s",
                        stream=sys.stdout)

    try:
        resumo = carregar(args.csv, args.db, args.coletado_em)
    except (CargaRecusada, ConfiguracaoError) as exc:
        print(f"Carga recusada: {exc}", file=sys.stderr)
        return 2

    print()
    print(f"  CSV .............. {args.csv.name}")
    print(f"  Coletado em ...... {args.coletado_em:%Y-%m-%d}")
    print(f"  Vagas criadas .... {resumo.jobs_criados}")
    print(f"  Vagas atualizadas  {resumo.jobs_atualizados}")
    print(f"  Snapshots novos .. {resumo.snapshots_criados}")
    print(f"  Falhas ........... {resumo.falhas}")
    return 1 if resumo.falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
