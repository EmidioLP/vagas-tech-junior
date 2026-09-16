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
    python main.py --respect-interval       # pula se COLLECTION_INTERVAL_DAYS nao passou

O banco (DATABASE_URL, com `alembic upgrade head` aplicado) e a fonte de verdade.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from scraper.config import SEARCH_TERMS, ConfiguracaoError, Settings
from scraper.execucao import GATILHOS, OK, ROTULOS
from scraper.pipeline import PipelineResult, run
from scraper.qualidade import ALTA
from scraper.sources import AVAILABLE_SOURCES, DEFAULT_SOURCES, FORA_DA_COLETA_PADRAO


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vagas-tech-junior",
        description="Descobre qual area de tecnologia tem mais vagas junior no Brasil.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--sources", nargs="+", default=list(DEFAULT_SOURCES),
        choices=AVAILABLE_SOURCES,
        help=f"Portais a consultar (padrão: {' '.join(DEFAULT_SOURCES)}; "
             f"fora do padrão, só se pedidos: {' '.join(FORA_DA_COLETA_PADRAO)}).",
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
        "--respect-interval", action="store_true",
        help="Consulta a ultima coleta completa registrada no banco e pula se ainda "
             "nao passaram COLLECTION_INTERVAL_DAYS dias (usado pelo agendamento).",
    )
    parser.add_argument(
        "--trigger", choices=GATILHOS, default="local",
        help="Quem disparou a execucao, gravado em collection_runs (padrao: local).",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Log detalhado (DEBUG)."
    )
    return parser


def _github_run_id() -> str | None:
    """`GITHUB_RUN_ID` do Actions, se for um numero. Liga log, resumo e registro."""
    valor = os.environ.get("GITHUB_RUN_ID", "").strip()
    return valor if valor.isdigit() else None


def _escrever_resumo(
    destino: Path | None,
    settings: Settings,
    codigo: int,
    result: PipelineResult | None = None,
    erro: str | None = None,
) -> None:
    """Grava o resumo pedido por `--resumo`.

    So entram contagens, nomes de fonte, status e tipos de erro, os mesmos dados
    impressos no terminal. Nada aqui carrega a URL do banco: `ConfiguracaoError`
    nunca a cita e os erros de persistencia tem o formato "fonte:id: TipoDoErro".
    """
    if destino is None:
        return

    if erro:
        status = "erro de configuração"
    elif result is None or result.status is None:
        status = "desconhecido"
    else:
        status = ROTULOS.get(result.status, result.status)

    linhas = [
        "## Coleta de vagas",
        "",
        f"- **Status:** {status} (exit {codigo})",
        f"- **Fontes:** {', '.join(settings.sources)}",
        f"- **Termos de busca:** {len(settings.search_terms)}",
        f"- **Páginas por termo:** {settings.max_pages_per_term}",
    ]
    if result is not None and result.agenda is not None:
        linhas.insert(3, f"- **{result.agenda.frase()}** ({result.agenda.periodicidade})")
    if erro:
        linhas.append(f"- **Erro:** {erro}")
    if result is not None:
        linhas += _resumo_da_execucao(result)

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def _resumo_da_execucao(result: PipelineResult) -> list[str]:
    meta = result.meta
    linhas: list[str] = []
    if meta.get("gatilho"):
        linhas.append(f"- **Gatilho:** {meta['gatilho']}")
    if meta.get("execucao_id"):
        linhas.append(f"- **Registro:** collection_runs.id {meta['execucao_id']}")
    if meta.get("github_run_id"):
        linhas.append(f"- **GitHub run:** {meta['github_run_id']}")
    if meta.get("motivo"):
        linhas.append(f"- **Motivo:** {meta['motivo']}")
    if meta.get("erro_registro"):
        linhas.append(f"- **Aviso:** {meta['erro_registro']}")

    if result.pulada:
        linhas.append(f"- **Verificada em (UTC):** {meta.get('collected_at', '-')}")
        return linhas

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
        "| Fonte | Status | Requests | Requests falhos | Vagas brutas | Avisos |",
        "|---|---|---:|---:|---:|---:|",
    ]
    stats = {s.source: s for s in result.stats}
    for fonte in dict.fromkeys([*result.status_fontes, *stats]):
        status = result.status_fontes.get(fonte)
        rotulo = ROTULOS.get(status, "-")
        if status not in (None, OK):
            rotulo = f"**{rotulo}**"  # fonte com falha nunca passa despercebida
        s = stats.get(fonte)
        numeros = (f"{s.requests_made} | {s.requests_failed} | {s.raw_jobs} | {len(s.errors)}"
                   if s is not None else "- | - | - | -")
        linhas.append(f"| {fonte} | {rotulo} | {numeros} |")

    linhas += ["", "### Qualidade", ""]
    if not result.alertas:
        linhas.append("Nenhum alerta. Regras e limites em `docs/data-quality.md`.")
    else:
        linhas += ["| Severidade | Regra | Fonte | Valor | Limite | Detalhe |",
                   "|---|---|---|---:|---:|---|"]
        for alerta in result.alertas:
            severidade = (f"**{alerta.severidade}**" if alerta.severidade == ALTA
                          else alerta.severidade)
            linhas.append(f"| {severidade} | {alerta.regra} | {alerta.fonte or '-'} "
                          f"| {alerta.valor} | {alerta.limite} | {alerta.mensagem} |")

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

        encerramento = result.encerramento
        linhas.append("")
        if encerramento is None:
            linhas.append("Nenhuma vaga avaliada para encerramento: só coletas completas, "
                          "com a fonte ok, encerram vagas.")
        else:
            linhas.append(
                f"**Vagas encerradas:** {encerramento.encerradas} (sumiram da listagem em 2 "
                f"coletas seguidas) · **ausentes pela 1ª vez:** {encerramento.ausentes} "
                "(encerram se continuarem fora na próxima coleta)"
            )
            linhas += [f"- `{e}`" for e in encerramento.erros]
    return linhas


def _imprimir_agenda(result: PipelineResult, recuo: str = "  ") -> None:
    """"Última coleta: dia ... e próxima: dia ..." (datas em UTC)."""
    if result.agenda is not None:
        print(f"{recuo}{result.agenda.frase()} ({result.agenda.periodicidade}).")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.no_db and not args.csv:
        parser.error("--no-db sem --csv não grava nada; use --csv junto.")
    if args.no_db and args.db:
        parser.error("--db e --no-db são incompatíveis.")
    if args.no_db and args.respect_interval:
        parser.error("--respect-interval consulta o banco; não combina com --no-db.")

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

    id_externo = _github_run_id()
    logging.getLogger("main").info(
        "Execução iniciada (%s)", f"GitHub run {id_externo}" if id_externo else "local")

    try:
        result = run(
            settings,
            strict_seniority=args.strict,
            keep_non_tech=args.keep_non_tech,
            with_charts=not args.no_charts,
            persistir=not args.no_db,
            destino_db=args.db,
            exportar_csv=args.csv,
            respeitar_intervalo=args.respect_interval,
            gatilho=args.trigger,
            id_externo=id_externo,
        )
    except ConfiguracaoError as exc:
        # A mensagem nunca inclui a URL do banco.
        print(f"\nErro de configuração: {exc}", file=sys.stderr)
        _escrever_resumo(args.resumo, settings, 2, erro=str(exc))
        return 2

    if result.pulada:
        print("\nColeta pulada: o intervalo entre coletas ainda não foi cumprido.")
        _imprimir_agenda(result, recuo="")
        if result.meta.get("erro_registro"):
            print(f"  ! {result.meta['erro_registro']}")
        _escrever_resumo(args.resumo, settings, result.exit_code, result=result)
        return result.exit_code

    if result.jobs:
        print("\n" + "=" * 62)
        print(f"  RANKING DE AREAS -- {len(result.jobs)} vagas junior/estagio/trainee")
        print("=" * 62)
        for row in result.ranking:
            bar = "#" * round(row["percentual"] / 2)
            print(f"  {row['posicao']:>2}. {row['area']:<18} {row['vagas']:>4} vagas "
                  f"({row['percentual']:>5.1f}%) {bar}")
        print("=" * 62)
        print(f"\n  Area com mais demanda junior: {result.top_area}")
    else:
        print("\nNenhuma vaga encontrada. Verifique conexao e termos de busca.")

    print(f"\n  Execução: {ROTULOS.get(result.status, result.status)}")
    for fonte, status in result.status_fontes.items():
        print(f"    {fonte:<16} {ROTULOS.get(status, status)}")
    if result.meta.get("motivo"):
        print(f"    Motivo: {result.meta['motivo']}")
    if result.meta.get("erro_registro"):
        print(f"    ! {result.meta['erro_registro']}")
    if result.alertas:
        print(f"\n  Qualidade ({len(result.alertas)} alerta(s)):")
        for alerta in result.alertas:
            marca = "!" if alerta.severidade == ALTA else "-"
            print(f"    {marca} [{alerta.severidade}] {alerta.mensagem}")
    if result.agenda is not None:
        print()
        _imprimir_agenda(result)

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
        encerramento = result.encerramento
        if encerramento is not None:
            print(f"    Vagas encerradas ..... {encerramento.encerradas}")
            print(f"    Ausentes (1ª vez) .... {encerramento.ausentes}")
            for erro in encerramento.erros:
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

    _escrever_resumo(args.resumo, settings, result.exit_code, result=result)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
