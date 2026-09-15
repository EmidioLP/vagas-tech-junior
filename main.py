"""CLI do vagas-tech-junior.

Exemplos:
    python main.py                          # coleta completa, grava no banco
    python main.py --csv                    # tambem exporta CSV, relatorio e graficos
    python main.py --no-db --csv            # so arquivos, sem banco
    python main.py --db data/teste.db       # outro banco (URL ou arquivo SQLite)
    python main.py --sources gupy           # so a Gupy
    python main.py --terms "estagio dados" "engenheiro de dados junior"
    python main.py --max-pages 2 --delay 2  # coleta menor e mais lenta
    python main.py --strict                 # descarta titulos "Junior/Pleno"
    python main.py --resumo coleta/resumo.md  # resumo Markdown sem dados sensiveis

O banco (DATABASE_URL, com `alembic upgrade head` aplicado) e a fonte de verdade.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from scraper.config import SEARCH_TERMS, ConfiguracaoError, Settings
from scraper.pipeline import PipelineResult, run
from scraper.sources import AVAILABLE_SOURCES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vagas-tech-junior",
        description="Descobre qual area de tecnologia tem mais vagas junior no Brasil.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--sources", nargs="+", default=list(AVAILABLE_SOURCES),
        choices=AVAILABLE_SOURCES,
        help=f"Portais a consultar (padrão: todos — {' '.join(AVAILABLE_SOURCES)}).",
    )
    parser.add_argument(
        "--terms", nargs="+", default=None,
        help=f"Termos de busca (padrao: {len(SEARCH_TERMS)} termos de config.py).",
    )
    parser.add_argument(
        "--max-pages", type=int, default=5,
        help="Maximo de paginas por termo, por portal (padrao: 5).",
    )
    parser.add_argument(
        "--page-size", type=int, default=100,
        help="Vagas por pagina; a Gupy aceita no maximo 100 (padrao: 100).",
    )
    parser.add_argument(
        "--delay", type=float, default=1.5,
        help="Segundos de espera entre requests (padrao: 1.5).",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Diretorio de saida (padrao: ./output).",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Descarta titulos mistos como 'Desenvolvedor Junior/Pleno'.",
    )
    parser.add_argument(
        "--all-levels", action="store_true",
        help="Nao filtra por senioridade (coleta tudo que os portais devolverem).",
    )
    parser.add_argument(
        "--keep-non-tech", action="store_true",
        help="Mantem vagas fora de tecnologia (Contabil, Fiscal...) que a busca "
             "solta dos portais devolve. Por padrao elas sao descartadas.",
    )
    parser.add_argument(
        "--csv", action="store_true",
        help="Exporta CSVs, relatorio .md e graficos em --output. Opcional: o "
             "banco e a fonte de verdade.",
    )
    parser.add_argument(
        "--no-db", action="store_true",
        help="Nao grava no banco. Exige --csv, senao a execucao nao guardaria nada.",
    )
    parser.add_argument(
        "--db", default=None, metavar="DESTINO",
        help="Banco de destino: URL (postgresql://...) ou caminho de arquivo SQLite. "
             "Padrao: DATABASE_URL.",
    )
    parser.add_argument(
        "--no-charts", action="store_true",
        help="Com --csv, nao gera os graficos PNG (util sem matplotlib).",
    )
    parser.add_argument(
        "--resumo", type=Path, default=None, metavar="ARQUIVO",
        help="Grava um resumo em Markdown, sem URL nem credenciais, em qualquer "
             "desfecho (usado pelo GitHub Actions).",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Log detalhado (DEBUG)."
    )
    return parser


def _escrever_resumo(
    destino: Path | None,
    settings: Settings,
    codigo: int,
    result: PipelineResult | None = None,
    erro: str | None = None,
) -> None:
    """Grava o resumo pedido por `--resumo`.

    So entram contagens, nomes de fonte e tipos de erro, os mesmos dados impressos
    no terminal. Nada aqui carrega a URL do banco: `ConfiguracaoError` nunca a cita
    e os erros de persistencia tem o formato "fonte:id: TipoDoErro".
    """
    if destino is None:
        return

    if erro:
        status = "erro de configuração"
    elif result is None or not result.jobs:
        status = "nenhuma vaga encontrada"
    elif codigo:
        status = "concluída com falhas"
    else:
        status = "concluída"

    linhas = [
        "## Coleta de vagas",
        "",
        f"- **Status:** {status} (exit {codigo})",
        f"- **Fontes:** {', '.join(settings.sources)}",
        f"- **Termos de busca:** {len(settings.search_terms)}",
        f"- **Páginas por termo:** {settings.max_pages_per_term}",
    ]
    if erro:
        linhas.append(f"- **Erro:** {erro}")

    if result is not None:
        meta = result.meta
        linhas += [
            f"- **Coletada em (UTC):** {meta.get('collected_at', '-')}",
            f"- **Requests:** {meta.get('requests', 0)}",
            "",
            "### Funil",
            "",
            "| Etapa | Vagas |",
            "|---|---:|",
            f"| Brutas | {meta.get('raw_jobs', 0)} |",
            f"| Fora da senioridade | -{meta.get('dropped_seniority', 0)} |",
            f"| Duplicadas | -{meta.get('duplicates', 0)} |",
            f"| Fora de tecnologia | -{meta.get('dropped_non_tech', 0)} |",
            f"| **Final** | **{len(result.jobs)}** |",
            "",
            "### Por fonte",
            "",
            "| Fonte | Requests | Vagas brutas | Avisos |",
            "|---|---:|---:|---:|",
        ]
        linhas += [
            f"| {s.source} | {s.requests_made} | {s.raw_jobs} | {len(s.errors)} |"
            for s in result.stats
        ]

        if result.ranking:
            linhas += ["", "### Ranking de áreas", "",
                       "| # | Área | Vagas | % |", "|---:|---|---:|---:|"]
            linhas += [
                f"| {r['posicao']} | {r['area']} | {r['vagas']} | {r['percentual']:.1f} |"
                for r in result.ranking
            ]

        resumo = result.persistencia
        linhas += ["", "### Banco (jobs / job_snapshots)", ""]
        if resumo is None:
            linhas.append("Não gravado (`--no-db`).")
        else:
            linhas += [
                "| Vagas criadas | Vagas atualizadas | Snapshots criados "
                "| Snapshots ignorados | Falhas |",
                "|---:|---:|---:|---:|---:|",
                f"| {resumo.jobs_criados} | {resumo.jobs_atualizados} "
                f"| {resumo.snapshots_criados} | {resumo.snapshots_ignorados} "
                f"| {resumo.falhas} |",
            ]
            if resumo.erros:
                linhas.append("")
                linhas += [f"- `{e}`" for e in resumo.erros[:10]]

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.no_db and not args.csv:
        parser.error("--no-db sem --csv não grava nada; use --csv junto.")
    if args.no_db and args.db:
        parser.error("--db e --no-db são incompatíveis.")

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )

    settings = Settings(
        search_terms=args.terms or list(SEARCH_TERMS),
        sources=args.sources,
        delay_seconds=args.delay,
        page_size=min(args.page_size, 100),
        max_pages_per_term=args.max_pages,
        only_junior=not args.all_levels,
    )
    if args.output:
        settings.output_dir = args.output

    try:
        result = run(
            settings,
            strict_seniority=args.strict,
            keep_non_tech=args.keep_non_tech,
            with_charts=not args.no_charts,
            persistir=not args.no_db,
            destino_db=args.db,
            exportar_csv=args.csv,
        )
    except ConfiguracaoError as exc:
        # A mensagem nunca inclui a URL do banco.
        print(f"\nErro de configuração: {exc}", file=sys.stderr)
        _escrever_resumo(args.resumo, settings, 2, erro=str(exc))
        return 2

    if not result.jobs:
        print("\nNenhuma vaga encontrada. Verifique conexao e termos de busca.")
        _escrever_resumo(args.resumo, settings, 1, result=result)
        return 1

    print("\n" + "=" * 62)
    print(f"  RANKING DE AREAS -- {len(result.jobs)} vagas junior/estagio/trainee")
    print("=" * 62)
    for row in result.ranking:
        bar = "#" * round(row["percentual"] / 2)
        print(f"  {row['posicao']:>2}. {row['area']:<18} {row['vagas']:>4} vagas "
              f"({row['percentual']:>5.1f}%) {bar}")
    print("=" * 62)
    print(f"\n  Area com mais demanda junior: {result.top_area}")

    resumo = result.persistencia
    if resumo is not None:
        print("\n  Banco (jobs / job_snapshots):")
        print(f"    Vagas criadas ........ {resumo.jobs_criados}")
        print(f"    Vagas atualizadas .... {resumo.jobs_atualizados}")
        print(f"    Snapshots criados .... {resumo.snapshots_criados}")
        print(f"    Snapshots ignorados .. {resumo.snapshots_ignorados}")
        print(f"    Falhas ............... {resumo.falhas}")
        for erro in resumo.erros[:10]:
            print(f"    ! {erro}")

    if result.files:
        print("\n  Arquivos gerados:")
        for label, path in result.files.items():
            print(f"    - {label:<12} {path}")

    errors = [e for s in result.stats for e in s.errors]
    if errors:
        print(f"\n  Avisos ({len(errors)}):")
        for err in errors[:10]:
            print(f"    ! {err}")

    codigo = 1 if resumo is not None and resumo.falhas else 0
    _escrever_resumo(args.resumo, settings, codigo, result=result)
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
