"""Mede o custo de `dashboard/consultas.serie_historica` e projeta o crescimento.

A serie historica e a unica analise do dashboard que nao agrega no SQL: ela traz
vagas e snapshots para a memoria e reconstroi cada dia de coleta em Python. O
numero que este script produz e o que calibra o gatilho para mover o agrupamento
para o banco (`docs/decisoes/0007-serie-historica-em-python.md`).

    python scripts/medir_serie_historica.py                 # banco configurado
    python scripts/medir_serie_historica.py --db data/x.db  # outro destino
    python scripts/medir_serie_historica.py --projetar 365  # historico sintetico

Somente leitura: no modo padrao so faz SELECT (o engine do dashboard ja abre em
modo leitura); no modo `--projetar` o historico sintetico vai para um arquivo
SQLite temporario, apagado no fim.

As taxas de crescimento do modo `--projetar` vieram dos logs do workflow de
coleta (execucoes de 17/09 e 19/09/2026): uma coleta a cada dois dias, cerca de
55 vagas novas e 67 snapshots por coleta, sobre uma base inicial de ~600 vagas.
"""

from __future__ import annotations

import argparse
import random
import sys
import tempfile
import time
import tracemalloc
from dataclasses import dataclass
from datetime import date, datetime, time as hora, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# --- taxas medidas na coleta real (ver docstring) ----------------------------

VAGAS_INICIAIS = 600
VAGAS_POR_COLETA = 55
# Snapshots por coleta menos as vagas novas: quantas vagas ja conhecidas mudaram.
MUDANCAS_POR_COLETA = 12
DIAS_ENTRE_COLETAS = 2
# Vida de uma vaga, em numero de coletas. A media (~11) mantem a base ativa
# perto das 600 vagas observadas: 55 novas x 11 coletas.
VIDA_MINIMA, VIDA_MAXIMA = 1, 21

FONTES = ("gupy", "linkedin", "vagas", "trampos", "querovagastech", "geekhunter",
          "solides")
# Taxonomia atual (ADR 0008). So varia os dados sinteticos, mas uma lista
# desatualizada aqui viraria documentacao errada da taxonomia.
AREAS = ("Suporte Técnico", "Engenharia de Software", "Backend", "Frontend", "Data",
         "Mobile", "DevOps", "QA", "Fullstack", "Sistemas / ERP",
         "Service Desk / Help Desk", "Infraestrutura / Redes", "Segurança",
         "Outros/TI Geral")
MODALIDADES = ("Remoto", "Híbrido", "Presencial", None)


@dataclass(frozen=True)
class Volume:
    vagas: int
    snapshots: int
    dias: int

    def __str__(self) -> str:
        return f"{self.vagas} vagas, {self.snapshots} snapshots, {self.dias} dias de coleta"


@dataclass(frozen=True)
class Medicao:
    segundos: float
    pico_mb: float
    pontos: int


def _momento(dia: date) -> datetime:
    return datetime.combine(dia, hora(9, 5), tzinfo=timezone.utc)


def gerar_historico(banco: Path, dias: int, semente: int = 20260921, *,
                    vagas_iniciais: int = VAGAS_INICIAIS,
                    vagas_por_coleta: int = VAGAS_POR_COLETA) -> Volume:
    """Popula um banco ja migrado com um historico sintetico de `dias` dias.

    Deterministico pela semente: o mesmo banco sai igual toda vez, para a
    medicao ser comparavel e para o teste de equivalencia ter um cenario fixo.
    As quantidades sao parametros para o teste rodar numa escala menor, com os
    mesmos casos de borda (vaga que nasce e fecha junto, troca de area, vaga sem
    snapshot no dia da estreia).
    """
    from sqlalchemy.orm import Session

    from api.database import make_engine
    from api.models import CollectionRun, JobRecord, JobSnapshot

    sorteio = random.Random(semente)
    primeiro_dia = date(2026, 9, 15)
    coletas = [primeiro_dia + timedelta(days=n * DIAS_ENTRE_COLETAS)
               for n in range(max(1, dias // DIAS_ENTRE_COLETAS))]

    vagas: list[JobRecord] = []
    # Vagas vivas: posicao na lista -> indice da coleta em que sera encerrada.
    vivas: dict[int, int] = {}

    for indice, dia in enumerate(coletas):
        quantas = vagas_iniciais if indice == 0 else vagas_por_coleta
        for _ in range(quantas):
            sequencia = len(vagas) + 1
            vagas.append(JobRecord(
                source=sorteio.choice(FONTES), external_id=f"sintetica-{sequencia}",
                url=f"https://portal.exemplo/vagas/{sequencia}",
                first_seen_at=_momento(dia), last_seen_at=_momento(dia), is_active=True,
                snapshots=[JobSnapshot(
                    collected_at=_momento(dia), title=f"Vaga {sequencia}", company="Acme",
                    area=sorteio.choice(AREAS), workplace_type=sorteio.choice(MODALIDADES),
                    content_hash=f"{sequencia}-0",
                )],
            ))
            vivas[len(vagas) - 1] = indice + sorteio.randint(VIDA_MINIMA, VIDA_MAXIMA)

        # Algumas vagas ja conhecidas mudam de estado e ganham um snapshot novo.
        # `(job_id, collected_at)` e unico, entao nunca duas no mesmo instante.
        candidatas = [posicao for posicao, fim in vivas.items() if fim > indice]
        for posicao in sorteio.sample(candidatas, min(MUDANCAS_POR_COLETA, len(candidatas))):
            vaga = vagas[posicao]
            if _momento(dia) <= vaga.snapshots[-1].collected_at:
                continue
            vaga.snapshots.append(JobSnapshot(
                collected_at=_momento(dia), title=vaga.snapshots[0].title, company="Acme",
                area=sorteio.choice(AREAS), workplace_type=sorteio.choice(MODALIDADES),
                content_hash=f"{posicao}-{len(vaga.snapshots)}",
            ))

        # Encerramento: a vaga sumiu da listagem e o pipeline a fechou nesta coleta.
        for posicao in [p for p, fim in vivas.items() if fim == indice]:
            vaga = vagas[posicao]
            vaga.is_active = False
            vaga.missing_since = _momento(dia)
            vaga.closed_at = _momento(dia)
            del vivas[posicao]

        for posicao in vivas:
            vagas[posicao].last_seen_at = _momento(dia)

    execucoes = [CollectionRun(
        started_at=_momento(dia), finished_at=_momento(dia), triggered_by="schedule",
        status="success", full_scope=True, interval_days=DIAS_ENTRE_COLETAS,
        jobs_count=vagas_iniciais, failures=0, summary={},
    ) for dia in coletas]

    # Contado antes de gravar: depois do commit as instancias ficam destacadas
    # da sessao e `vaga.snapshots` viraria lazy load.
    total_snapshots = sum(len(vaga.snapshots) for vaga in vagas)

    engine = make_engine(banco)
    try:
        with Session(engine) as db, db.begin():
            db.add_all(vagas)
            db.add_all(execucoes)
    finally:
        engine.dispose()

    return Volume(len(vagas), total_snapshots, len(coletas))


def banco_sintetico(destino: Path, dias: int, semente: int = 20260921) -> Volume:
    """Cria o arquivo, aplica `alembic upgrade head` e popula."""
    from alembic import command
    from alembic.config import Config

    from scraper import config

    cfg = Config(str(config.PROJECT_ROOT / "alembic.ini"))
    cfg.attributes["database_url"] = f"sqlite:///{destino.as_posix()}"
    command.upgrade(cfg, "head")
    return gerar_historico(destino, dias, semente)


def serie_referencia(engine, filtros):
    """Implementacao **anterior** da serie: um laco por dia sobre todas as vagas.

    Fica aqui como oraculo, nao como codigo vivo: e ela que define o resultado
    correto. `dashboard/consultas.serie_historica` passou a varrer por vaga
    (ADR 0007) e precisa concordar com esta em todo banco e todo filtro. Usada
    pelo `--comparar` e por `tests/dashboard/test_serie_equivalencia.py`.

    Nao otimizar. O valor dela esta em ser a versao que ja rodou em producao.
    """
    from bisect import bisect_left
    from collections import Counter, defaultdict
    from datetime import date, datetime, timedelta

    from sqlalchemy import or_, select

    from api.models import CollectionRun, JobRecord, JobSnapshot
    from dashboard.consultas import (PontoSerie, _inicio_do_dia, _leitura, _limites,
                                     _passa, _utc)
    from persistence.foto_atual import rotulo_area, rotulo_modalidade
    from persistence.frescor import STATUS_QUE_CONTAM

    inicio, fim = _limites(filtros)
    execucoes = select(CollectionRun.started_at).where(CollectionRun.status.in_(STATUS_QUE_CONTAM))
    if inicio is not None:
        execucoes = execucoes.where(CollectionRun.started_at >= inicio)
    if fim is not None:
        execucoes = execucoes.where(CollectionRun.started_at < fim)

    with _leitura(engine) as db:
        dias = sorted({_utc(momento).date() for momento in db.scalars(execucoes)})
        if not dias:
            return []
        primeiro = _inicio_do_dia(dias[0])
        limite = _inicio_do_dia(dias[-1] + timedelta(days=1))

        vagas = select(JobRecord.id, JobRecord.first_seen_at, JobRecord.closed_at).where(
            JobRecord.first_seen_at < limite,
            or_(JobRecord.closed_at.is_(None), JobRecord.closed_at >= primeiro),
        )
        if filtros.fontes:
            vagas = vagas.where(JobRecord.source.in_(filtros.fontes))
        linhas_vagas = db.execute(vagas).all()

        ids = vagas.with_only_columns(JobRecord.id)
        snapshots = db.execute(
            select(JobSnapshot.job_id, JobSnapshot.collected_at,
                   rotulo_area(JobSnapshot.area), rotulo_modalidade(JobSnapshot.workplace_type))
            .where(JobSnapshot.job_id.in_(ids), JobSnapshot.collected_at < limite)
            .order_by(JobSnapshot.job_id, JobSnapshot.collected_at)
        ).all()

    momentos: dict[int, list[datetime]] = defaultdict(list)
    estados: dict[int, list[tuple[str, str]]] = defaultdict(list)
    snapshots_por_dia: Counter[date] = Counter()
    for job_id, coletado_em, area, modalidade in snapshots:
        coletado_em = _utc(coletado_em)
        momentos[job_id].append(coletado_em)
        estados[job_id].append((area, modalidade))
        if _passa(filtros, area, modalidade):
            snapshots_por_dia[coletado_em.date()] += 1

    pontos = []
    for dia in dias:
        fim_do_dia = _inicio_do_dia(dia + timedelta(days=1))
        abertas = novas = 0
        por_area: Counter[str] = Counter()
        for job_id, primeiro_avistamento, encerrada_em in linhas_vagas:
            primeiro_avistamento = _utc(primeiro_avistamento)
            if primeiro_avistamento >= fim_do_dia:
                continue
            posicao = bisect_left(momentos[job_id], fim_do_dia) - 1
            if posicao < 0:
                continue
            area, modalidade = estados[job_id][posicao]
            if not _passa(filtros, area, modalidade):
                continue
            if primeiro_avistamento.date() == dia:
                novas += 1
            if encerrada_em is None or _utc(encerrada_em) >= fim_do_dia:
                abertas += 1
                por_area[area] += 1
        pontos.append(PontoSerie(dia, abertas, novas, snapshots_por_dia[dia], dict(por_area)))
    return pontos


def contar(engine) -> Volume:
    from sqlalchemy import func, select

    from api.models import CollectionRun, JobRecord, JobSnapshot
    # `_leitura` converte erro de driver em DadosIndisponiveis, que so carrega o
    # tipo do erro: a mensagem original citaria host e usuario do banco.
    from dashboard.consultas import _leitura
    from persistence.frescor import STATUS_QUE_CONTAM

    with _leitura(engine) as db:
        vagas = db.scalar(select(func.count()).select_from(JobRecord))
        snapshots = db.scalar(select(func.count()).select_from(JobSnapshot))
        dias = len({momento.date() for momento in db.scalars(
            select(CollectionRun.started_at).where(CollectionRun.status.in_(STATUS_QUE_CONTAM))
        )})
    return Volume(vagas or 0, snapshots or 0, dias)


def medir(engine, repeticoes: int = 3) -> Medicao:
    """Serie do periodo completo (`Filtros()`), que e o padrao da tela."""
    from dashboard.consultas import Filtros, serie_historica

    filtros = Filtros()
    pontos = serie_historica(engine, filtros)  # aquece: conexao aberta, plano em cache

    tracemalloc.start()
    melhor = None
    for _ in range(repeticoes):
        inicio = time.perf_counter()
        pontos = serie_historica(engine, filtros)
        decorrido = time.perf_counter() - inicio
        melhor = decorrido if melhor is None else min(melhor, decorrido)
    _, pico = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return Medicao(melhor or 0.0, pico / 1024 / 1024, len(pontos))


def combinacoes(engine) -> list:
    """Filtros tirados do vocabulario que existe no banco, nao de uma lista fixa.

    Cobre o padrao da tela (periodo completo, sem filtro), cada dimensao sozinha,
    as tres juntas e recortes de periodo nas pontas e no meio.
    """
    from dashboard.consultas import Filtros, opcoes_filtro

    opcoes = opcoes_filtro(engine)
    combos = [Filtros()]
    for fonte in opcoes.fontes:
        combos.append(Filtros(fontes=(fonte,)))
    for area in opcoes.areas:
        combos.append(Filtros(areas=(area,)))
    for modalidade in opcoes.modalidades:
        combos.append(Filtros(modalidades=(modalidade,)))
    if opcoes.fontes and opcoes.areas and opcoes.modalidades:
        combos.append(Filtros(fontes=opcoes.fontes[:2], areas=opcoes.areas[:2],
                              modalidades=opcoes.modalidades[:1]))
    if opcoes.primeiro_dia and opcoes.ultimo_dia:
        primeiro, ultimo = opcoes.primeiro_dia, opcoes.ultimo_dia
        meio = primeiro + (ultimo - primeiro) / 2
        combos += [
            Filtros(inicio=primeiro, fim=primeiro),          # so o primeiro dia
            Filtros(inicio=ultimo, fim=ultimo),              # so o ultimo
            Filtros(inicio=meio, fim=ultimo),                # segunda metade
            Filtros(inicio=primeiro, fim=meio),              # primeira metade
            Filtros(inicio=ultimo + timedelta(days=365), fim=ultimo + timedelta(days=400)),
        ]
        if opcoes.areas:
            combos.append(Filtros(areas=opcoes.areas[:1], inicio=meio, fim=ultimo))
    return combos


def comparar(engine) -> int:
    """Roda as duas implementacoes no mesmo banco e confere ponto a ponto.

    Devolve quantos filtros divergiram. Nao imprime nada do banco alem de
    contagens e rotulos de filtro: nunca URL, host nem usuario.
    """
    from dashboard.consultas import DadosIndisponiveis, serie_historica

    combos = combinacoes(engine)
    divergencias = 0
    for filtros in combos:
        try:
            nova = serie_historica(engine, filtros)
            antiga = serie_referencia(engine, filtros)
        except DadosIndisponiveis:
            raise
        except Exception as erro:  # noqa: BLE001 - qualquer falha e divergencia
            divergencias += 1
            print(f"  ERRO em {_rotulo(filtros)}: {type(erro).__name__}")
            continue
        if nova == antiga:
            continue
        divergencias += 1
        print(f"  DIVERGIU em {_rotulo(filtros)}")
        for esquerda, direita in zip(nova, antiga):
            if esquerda != direita:
                print(f"    dia {esquerda.dia}: nova={esquerda} antiga={direita}")
        if len(nova) != len(antiga):
            print(f"    numero de pontos: nova={len(nova)} antiga={len(antiga)}")

    pontos = len(serie_historica(engine, combos[0]))
    print(f"  Filtros conferidos .. {len(combos)}")
    print(f"  Pontos na serie ..... {pontos} (periodo completo)")
    if divergencias:
        print(f"  RESULTADO ........... {divergencias} divergencia(s)")
    else:
        print("  RESULTADO ........... identicas em todos os filtros")
    return divergencias


def _rotulo(filtros) -> str:
    partes = []
    for nome in ("fontes", "areas", "modalidades"):
        valores = getattr(filtros, nome)
        if valores:
            partes.append(f"{nome}={list(valores)}")
    if filtros.inicio or filtros.fim:
        partes.append(f"periodo={filtros.inicio}..{filtros.fim}")
    return ", ".join(partes) or "sem filtro (padrao da tela)"


def _relatar(volume: Volume, medicao: Medicao) -> None:
    print(f"  Volume ........ {volume}")
    print(f"  Pontos ........ {medicao.pontos}")
    print(f"  Tempo ......... {medicao.segundos:.3f}s (melhor de 3)")
    print(f"  Pico memoria .. {medicao.pico_mb:.1f} MB")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", help="URL ou caminho SQLite. Sem isso: DASHBOARD_DB ou DATABASE_URL.")
    ap.add_argument("--projetar", type=int, metavar="DIAS",
                    help="mede contra um historico sintetico de DIAS dias, num SQLite temporario")
    ap.add_argument("--semente", type=int, default=20260921,
                    help="semente do historico sintetico (padrao: %(default)s)")
    ap.add_argument("--comparar", action="store_true",
                    help="confere a varredura atual contra a implementacao anterior, ponto a ponto")
    args = ap.parse_args(argv)

    from dashboard import config as config_dashboard

    if args.projetar is not None:
        if args.projetar < DIAS_ENTRE_COLETAS:
            ap.error(f"--projetar precisa de pelo menos {DIAS_ENTRE_COLETAS} dias.")
        with tempfile.TemporaryDirectory() as pasta:
            banco = Path(pasta) / "projecao.db"
            print(f"Historico sintetico de {args.projetar} dias (semente {args.semente}):")
            volume = banco_sintetico(banco, args.projetar, args.semente)
            engine = config_dashboard.criar_engine(banco)
            try:
                if args.comparar:
                    return 1 if comparar(engine) else 0
                _relatar(volume, medir(engine))
            finally:
                engine.dispose()
        return 0

    from sqlalchemy.exc import ArgumentError

    from scraper.config import ConfiguracaoError

    try:
        engine = config_dashboard.criar_engine(args.db)
    except ConfiguracaoError as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 2
    except ArgumentError:
        # A mensagem do SQLAlchemy nao cita a URL, mas o traceback inteiro nao tem
        # o que fazer num utilitario que le banco de producao: so o diagnostico.
        print("Erro: a URL do banco nao pode ser interpretada. Confira se o valor "
              "tem so a URL: sem aspas em volta, sem o prefixo 'DATABASE_URL = ' "
              "e sem quebra de linha.", file=sys.stderr)
        return 2
    from dashboard.consultas import DadosIndisponiveis

    try:
        print("Banco configurado:")
        if args.comparar:
            print(f"  Volume ........ {contar(engine)}")
            return 1 if comparar(engine) else 0
        _relatar(contar(engine), medir(engine))
    except DadosIndisponiveis as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 2
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
