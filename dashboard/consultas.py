"""Unica camada de acesso ao banco do dashboard. So le.

Funcoes puras que recebem o engine, testaveis sem Streamlit. Os criterios seguem
os contratos do pipeline, sem reimplementar regra nenhuma:

- **ultima coleta:** a mesma regra da guarda de intervalo (`scraper/execucao.py`):
  execucao de escopo completo com status `success` ou `partial`;
- **proxima coleta:** o `next_run_on` gravado pela execucao mais recente;
- **vaga ativa:** `jobs.is_active` (encerramento em `persistence/repositorio.py`);
- **estado atual:** `persistence/foto_atual.vagas_atuais`, a mesma consulta da API.

Vocabulario das analises (o mesmo da tela e do dashboard/README.md):

- **vaga unica:** uma linha de `jobs`, identidade `(source, external_id)`. Toda
  contagem de "vagas" conta `jobs`, nunca snapshots;
- **snapshot:** uma linha de `job_snapshots`. O pipeline so grava quando o estado
  da vaga muda, entao snapshots por dia contam mudancas observadas, nao vagas
  vistas;
- **estado atual:** o snapshot mais recente da vaga; **estado vigente num dia:** o
  ultimo snapshot gravado ate o fim daquele dia (UTC);
- **dia de coleta:** dia UTC com execucao `success` ou `partial`, de qualquer escopo.

Filtros viram sempre bind params (`in_`, comparacoes): nada e interpolado no SQL.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from collections import Counter, defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import urlsplit

from sqlalchemy import case, distinct, func, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from api.models import CollectionRun, JobRecord, JobSnapshot, Tecnologia, job_snapshot_tecnologias
# SEM_AREA e reexportado: e o rotulo que a tela mostra para snapshot sem area.
from persistence.frescor import STATUS_QUE_CONTAM, Frescor, estado_das_coletas
from persistence.foto_atual import SEM_AREA, rotulo_area, rotulo_modalidade, vagas_atuais  # noqa: F401
from scraper.models import NAO_INFORMADO, REMOTO, WORKPLACE_ORDER


# Abaixo disso o ranking de tecnologias oscila demais para ser lido (README, "Limitações").
BASE_MINIMA_TECNOLOGIAS = 30
# Por area, o painel aparece a partir de 15 vagas na base (o limite que o README
# chama de confiavel), marcado como indicativo ate `BASE_MINIMA_TECNOLOGIAS`.
BASE_MINIMA_POR_AREA = 15

DIMENSOES = ("area", "modalidade", "fonte")


class DadosIndisponiveis(RuntimeError):
    """Banco inacessivel, sem configuracao ou sem schema.

    A mensagem so traz o tipo do erro: a do driver pode citar host, usuario ou
    caminho do arquivo.
    """


@dataclass(frozen=True)
class Coleta:
    iniciada_em: datetime
    status: str
    vagas: int


@dataclass(frozen=True)
class Execucao:
    iniciada_em: datetime
    status: str
    gatilho: str


@dataclass(frozen=True)
class ResumoGeral:
    ultima_coleta: Coleta | None
    proxima_coleta: date | None
    ultima_execucao: Execucao | None
    vagas_ativas: int
    # Em dia, vencido ou coleta parada (persistence/frescor.py).
    frescor: Frescor | None = None

    @property
    def vazio(self) -> bool:
        return self.ultima_coleta is None and self.vagas_ativas == 0


@dataclass(frozen=True)
class Filtros:
    """Tupla vazia = sem filtro. `inicio`/`fim` sao dias UTC, ambos inclusivos.

    Hashavel, para servir de chave do `st.cache_data`.
    """

    fontes: tuple[str, ...] = ()
    areas: tuple[str, ...] = ()
    modalidades: tuple[str, ...] = ()
    inicio: date | None = None
    fim: date | None = None


@dataclass(frozen=True)
class OpcoesFiltro:
    fontes: tuple[str, ...]
    areas: tuple[str, ...]
    modalidades: tuple[str, ...]
    primeiro_dia: date | None
    ultimo_dia: date | None


@dataclass(frozen=True)
class Indicadores:
    """Fotografia atual: vagas unicas ativas, classificadas pelo estado atual."""

    vagas_ativas: int
    empresas: int
    remotas: int
    sem_modalidade: int
    fontes: int

    @property
    def percentual_remoto(self) -> float | None:
        """Remotas sobre todas as ativas. Sem vagas nao ha percentual (nunca 0%)."""
        if self.vagas_ativas == 0:
            return None
        return 100 * self.remotas / self.vagas_ativas


@dataclass(frozen=True)
class Contagem:
    rotulo: str
    vagas: int


@dataclass(frozen=True)
class PontoSerie:
    """Um dia de coleta.

    - `abertas`: vagas unicas abertas no fim do dia, pelo estado vigente;
    - `novas`: vagas unicas vistas pela primeira vez no dia;
    - `snapshots`: snapshots gravados no dia (mudancas de estado, nao vagas).
    """

    dia: date
    abertas: int
    novas: int
    snapshots: int
    abertas_por_area: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class LinhaVaga:
    titulo: str
    empresa: str | None
    area: str
    modalidade: str
    fonte: str
    primeiro_avistamento: datetime
    ultimo_avistamento: datetime
    ativa: bool
    url: str | None


@dataclass(frozen=True)
class PaginaVagas:
    linhas: tuple[LinhaVaga, ...]
    total: int
    pagina: int
    por_pagina: int

    @property
    def paginas(self) -> int:
        return max(1, math.ceil(self.total / self.por_pagina))


@dataclass(frozen=True)
class RankingTecnologias:
    """`base`: vagas ativas (do recorte) que citam ao menos uma tecnologia."""

    base: int
    vagas_ativas: int
    itens: tuple[Contagem, ...]

    @property
    def confiavel(self) -> bool:
        return self.base >= BASE_MINIMA_TECNOLOGIAS


@dataclass(frozen=True)
class TecnologiasDaArea:
    area: str
    ranking: RankingTecnologias

    @property
    def exibivel(self) -> bool:
        return self.ranking.base >= BASE_MINIMA_POR_AREA


def _utc(momento: datetime) -> datetime:
    """O SQLite devolve datetime sem fuso; o valor gravado ja esta em UTC."""
    if momento.tzinfo is None:
        return momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(timezone.utc)


def _inicio_do_dia(dia: date) -> datetime:
    return datetime.combine(dia, time.min, tzinfo=timezone.utc)


def _limites(filtros: Filtros) -> tuple[datetime | None, datetime | None]:
    """Periodo como [inicio, fim) em UTC; o dia `fim` entra inteiro."""
    inicio = _inicio_do_dia(filtros.inicio) if filtros.inicio else None
    fim = _inicio_do_dia(filtros.fim + timedelta(days=1)) if filtros.fim else None
    return inicio, fim


@contextmanager
def _leitura(engine: Engine) -> Iterator[Session]:
    try:
        with Session(engine) as db:
            yield db
    except SQLAlchemyError as exc:
        tipo = type(getattr(exc, "orig", None) or exc).__name__
        raise DadosIndisponiveis(f"Não foi possível ler o banco ({tipo}).") from exc


def ultima_coleta(engine: Engine) -> Coleta | None:
    with _leitura(engine) as db:
        linha = db.execute(
            select(CollectionRun.started_at, CollectionRun.status, CollectionRun.jobs_count)
            .where(CollectionRun.full_scope.is_(True),
                   CollectionRun.status.in_(STATUS_QUE_CONTAM))
            .order_by(CollectionRun.started_at.desc())
            .limit(1)
        ).first()
    if linha is None:
        return None
    return Coleta(_utc(linha.started_at), linha.status, linha.jobs_count)


def proxima_coleta(engine: Engine) -> date | None:
    with _leitura(engine) as db:
        return db.scalar(
            select(CollectionRun.next_run_on)
            .where(CollectionRun.next_run_on.is_not(None))
            .order_by(CollectionRun.started_at.desc())
            .limit(1)
        )


def ultima_execucao(engine: Engine) -> Execucao | None:
    """Execucao mais recente de qualquer status, inclusive pulada ou com falha."""
    with _leitura(engine) as db:
        linha = db.execute(
            select(CollectionRun.started_at, CollectionRun.status, CollectionRun.triggered_by)
            .order_by(CollectionRun.started_at.desc())
            .limit(1)
        ).first()
    if linha is None:
        return None
    return Execucao(_utc(linha.started_at), linha.status, linha.triggered_by)


def vagas_ativas(engine: Engine) -> int:
    with _leitura(engine) as db:
        total = db.scalar(
            select(func.count()).select_from(JobRecord).where(JobRecord.is_active.is_(True))
        )
    return total or 0


def frescor(engine: Engine) -> Frescor:
    """A mesma regra de frescor de `/health/dados` na API."""
    with _leitura(engine) as db:
        return estado_das_coletas(db)


def resumo_geral(engine: Engine) -> ResumoGeral:
    return ResumoGeral(
        ultima_coleta=ultima_coleta(engine),
        proxima_coleta=proxima_coleta(engine),
        ultima_execucao=ultima_execucao(engine),
        vagas_ativas=vagas_ativas(engine),
        frescor=frescor(engine),
    )


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


def _filtrar(stmt, vagas, filtros: Filtros):
    """Fonte, area e modalidade sobre o estado atual. O periodo e de cada consulta."""
    if filtros.fontes:
        stmt = stmt.where(vagas.c.fonte.in_(filtros.fontes))
    if filtros.areas:
        stmt = stmt.where(vagas.c.area.in_(filtros.areas))
    if filtros.modalidades:
        stmt = stmt.where(vagas.c.modalidade.in_(filtros.modalidades))
    return stmt


def _ordem_modalidades(valores) -> tuple[str, ...]:
    conhecidas = [m for m in WORKPLACE_ORDER if m in valores]
    return tuple(conhecidas + sorted(set(valores) - set(conhecidas)))


def opcoes_filtro(engine: Engine) -> OpcoesFiltro:
    """Valores que existem no banco e o intervalo de dias de coleta."""
    with _leitura(engine) as db:
        fontes = db.scalars(select(distinct(JobRecord.source)).order_by(JobRecord.source)).all()
        area = rotulo_area(JobSnapshot.area)
        areas = db.scalars(select(distinct(area)).order_by(area)).all()
        modalidades = db.scalars(select(distinct(rotulo_modalidade(JobSnapshot.workplace_type)))).all()
        primeiro, ultimo = db.execute(
            select(func.min(CollectionRun.started_at), func.max(CollectionRun.started_at))
            .where(CollectionRun.status.in_(STATUS_QUE_CONTAM))
        ).one()
    return OpcoesFiltro(
        fontes=tuple(fontes),
        areas=tuple(areas),
        modalidades=_ordem_modalidades(modalidades),
        primeiro_dia=_utc(primeiro).date() if primeiro else None,
        ultimo_dia=_utc(ultimo).date() if ultimo else None,
    )


def indicadores_atuais(engine: Engine, filtros: Filtros) -> Indicadores:
    """KPIs das vagas unicas ativas. O periodo nao se aplica: e a fotografia de agora."""
    vagas = vagas_atuais()
    empresa = func.nullif(func.lower(func.trim(vagas.c.empresa)), "")
    stmt = _filtrar(
        select(
            func.count(),
            func.count(distinct(empresa)),
            func.coalesce(func.sum(case((vagas.c.modalidade == REMOTO, 1), else_=0)), 0),
            func.coalesce(func.sum(case((vagas.c.modalidade == NAO_INFORMADO, 1), else_=0)), 0),
            func.count(distinct(vagas.c.fonte)),
        ).where(vagas.c.ativa.is_(True)),
        vagas, filtros,
    )
    with _leitura(engine) as db:
        total, empresas, remotas, sem_modalidade, fontes = db.execute(stmt).one()
    return Indicadores(total, empresas, int(remotas), int(sem_modalidade), fontes)


def distribuicao(engine: Engine, filtros: Filtros, dimensao: str) -> list[Contagem]:
    """Vagas unicas ativas por area, modalidade ou fonte (estado atual)."""
    if dimensao not in DIMENSOES:
        raise ValueError(f"Dimensão desconhecida: {dimensao!r}")
    vagas = vagas_atuais()
    coluna = vagas.c[dimensao]
    quantidade = func.count().label("vagas")
    stmt = _filtrar(
        select(coluna, quantidade).where(vagas.c.ativa.is_(True)), vagas, filtros
    ).group_by(coluna).order_by(quantidade.desc(), coluna)
    with _leitura(engine) as db:
        return [Contagem(rotulo, total) for rotulo, total in db.execute(stmt)]


def _passa(filtros: Filtros, area: str, modalidade: str) -> bool:
    return ((not filtros.areas or area in filtros.areas)
            and (not filtros.modalidades or modalidade in filtros.modalidades))


def serie_historica(engine: Engine, filtros: Filtros) -> list[PontoSerie]:
    """Um ponto por dia de coleta no periodo.

    O agrupamento por dia e feito aqui, em UTC, porque `date()` sobre `timestamptz`
    depende do fuso da sessao. Area e modalidade de cada vaga vem do estado
    vigente no fim do dia, entao uma vaga que mudou de Backend para Data conta
    em Backend antes da mudanca e em Data depois.

    A varredura e **por vaga**, nao por dia: cada vaga visita so os dias entre a
    estreia e o encerramento, com um ponteiro que avanca sobre os proprios
    snapshots. Visitar todas as vagas em todos os dias custaria O(dias x vagas),
    que cresce ao quadrado no tempo, porque o periodo padrao da tela e o
    historico inteiro e os dois crescem juntos (ADR 0007).
    """
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

    # Fim (exclusivo) de cada dia, em ordem: e sobre esta lista que cada vaga
    # localiza a propria janela por bisect, em vez de percorrer todos os dias.
    fins = [_inicio_do_dia(dia + timedelta(days=1)) for dia in dias]
    abertas = [0] * len(dias)
    novas = [0] * len(dias)
    por_area: list[Counter[str]] = [Counter() for _ in dias]

    for job_id, primeiro_avistamento, encerrada_em in linhas_vagas:
        estreia = _utc(primeiro_avistamento)
        encerramento = _utc(encerrada_em) if encerrada_em is not None else None
        # Primeiro dia que termina depois da estreia; antes dele a vaga nao existia.
        comeco = bisect_right(fins, estreia)
        if comeco >= len(dias):
            continue
        # Ultimo dia que termina ate o encerramento: depois dele ela nao esta aberta.
        fechamento = len(dias) - 1 if encerramento is None else bisect_right(fins, encerramento) - 1
        # O dia de estreia e sempre visitado, mesmo se a vaga fechou nele: e o
        # unico dia em que ela pode contar como nova.
        fechamento = max(fechamento, comeco)

        momentos_da_vaga = momentos.get(job_id, ())
        estados_da_vaga = estados.get(job_id, ())
        # Ultimo snapshot ate o fim do dia corrente. So anda para a frente, entao
        # o custo por vaga e o numero de snapshots dela, nao um bisect por dia.
        posicao = -1
        for indice in range(comeco, fechamento + 1):
            fim_do_dia = fins[indice]
            while (posicao + 1 < len(momentos_da_vaga)
                   and momentos_da_vaga[posicao + 1] < fim_do_dia):
                posicao += 1
            if posicao < 0:
                continue  # sem snapshot ate aqui: a vaga ainda nao tem estado vigente
            area, modalidade = estados_da_vaga[posicao]
            if not _passa(filtros, area, modalidade):
                continue
            if estreia.date() == dias[indice]:
                novas[indice] += 1
            if encerramento is None or encerramento >= fim_do_dia:
                abertas[indice] += 1
                por_area[indice][area] += 1

    return [PontoSerie(dia, abertas[i], novas[i], snapshots_por_dia[dia], dict(por_area[i]))
            for i, dia in enumerate(dias)]


def url_segura(url: str | None) -> str | None:
    """So links http(s) absolutos viram link na tela; `javascript:` e afins nao."""
    if not url:
        return None
    try:
        partes = urlsplit(url.strip())
    except ValueError:
        return None
    if partes.scheme.lower() not in ("http", "https") or not partes.netloc:
        return None
    return url.strip()


def listar_vagas(engine: Engine, filtros: Filtros, somente_ativas: bool = True,
                 pagina: int = 1, por_pagina: int = 50) -> PaginaVagas:
    """Vagas unicas com o estado atual, da mais recentemente vista para a mais antiga.

    O periodo seleciona vagas **vistas** nele: primeira vez antes do fim e ultima
    vez depois do inicio.
    """
    pagina = max(1, pagina)
    vagas = vagas_atuais()
    stmt = _filtrar(select(vagas), vagas, filtros)
    if somente_ativas:
        stmt = stmt.where(vagas.c.ativa.is_(True))
    inicio, fim = _limites(filtros)
    if inicio is not None:
        stmt = stmt.where(vagas.c.ultimo_avistamento >= inicio)
    if fim is not None:
        stmt = stmt.where(vagas.c.primeiro_avistamento < fim)

    with _leitura(engine) as db:
        total = db.scalar(select(func.count()).select_from(stmt.subquery()))
        linhas = db.execute(
            stmt.order_by(vagas.c.ultimo_avistamento.desc(), vagas.c.job_id)
            .limit(por_pagina).offset((pagina - 1) * por_pagina)
        ).all()
    return PaginaVagas(
        linhas=tuple(
            LinhaVaga(
                titulo=linha.titulo,
                empresa=linha.empresa,
                area=linha.area,
                modalidade=linha.modalidade,
                fonte=linha.fonte,
                primeiro_avistamento=_utc(linha.primeiro_avistamento),
                ultimo_avistamento=_utc(linha.ultimo_avistamento),
                ativa=bool(linha.ativa),
                url=url_segura(linha.url),
            )
            for linha in linhas
        ),
        total=total or 0,
        pagina=pagina,
        por_pagina=por_pagina,
    )


def _recorte_tecnologias(filtros: Filtros):
    """Vagas unicas ativas do filtro (estado atual) e o join com as tecnologias citadas."""
    vagas = vagas_atuais()
    recorte = _filtrar(
        select(vagas.c.job_id, vagas.c.snapshot_id, vagas.c.area).where(vagas.c.ativa.is_(True)),
        vagas, filtros,
    ).subquery("recorte")
    citacoes = recorte.join(job_snapshot_tecnologias,
                            job_snapshot_tecnologias.c.snapshot_id == recorte.c.snapshot_id)
    return recorte, citacoes


def top_tecnologias(engine: Engine, filtros: Filtros, limite: int = 15) -> RankingTecnologias:
    """Tecnologias citadas no estado atual das vagas unicas ativas.

    Mede mencao, nao exigencia. A base do percentual sao as vagas que citam alguma
    tecnologia: o card do LinkedIn nao tem descricao e quase nunca cita.
    """
    recorte, citacoes = _recorte_tecnologias(filtros)
    quantidade = func.count(distinct(recorte.c.job_id)).label("vagas")

    with _leitura(engine) as db:
        total = db.scalar(select(func.count()).select_from(recorte))
        base = db.scalar(select(func.count(distinct(recorte.c.job_id))).select_from(citacoes))
        itens = db.execute(
            select(Tecnologia.nome, quantidade)
            .select_from(citacoes.join(Tecnologia,
                                       Tecnologia.id == job_snapshot_tecnologias.c.tecnologia_id))
            .group_by(Tecnologia.nome)
            .order_by(quantidade.desc(), Tecnologia.nome)
            .limit(limite)
        ).all()
    return RankingTecnologias(
        base=base or 0,
        vagas_ativas=total or 0,
        itens=tuple(Contagem(nome, vagas) for nome, vagas in itens),
    )


def tecnologias_por_area(engine: Engine, filtros: Filtros, limite: int = 8) -> list[TecnologiasDaArea]:
    """O ranking de `top_tecnologias` separado por area (estado atual das ativas).

    Cada area tem a propria base: as vagas ativas dela que citam alguma tecnologia.
    Volta toda area com vaga ativa no filtro, inclusive as de base pequena, para a
    tela dizer quais ficaram de fora. Ordem: maior base primeiro.
    """
    recorte, citacoes = _recorte_tecnologias(filtros)
    quantidade = func.count(distinct(recorte.c.job_id))

    with _leitura(engine) as db:
        totais = dict(db.execute(
            select(recorte.c.area, func.count()).group_by(recorte.c.area)).all())
        bases = dict(db.execute(
            select(recorte.c.area, quantidade).select_from(citacoes).group_by(recorte.c.area)).all())
        contagens = db.execute(
            select(recorte.c.area, Tecnologia.nome, quantidade)
            .select_from(citacoes.join(Tecnologia,
                                       Tecnologia.id == job_snapshot_tecnologias.c.tecnologia_id))
            .group_by(recorte.c.area, Tecnologia.nome)
        ).all()

    por_area: dict[str, list[Contagem]] = defaultdict(list)
    for area, nome, vagas in contagens:
        por_area[area].append(Contagem(nome, vagas))

    areas = sorted(totais, key=lambda area: (-bases.get(area, 0), area))
    return [
        TecnologiasDaArea(area, RankingTecnologias(
            base=bases.get(area, 0),
            vagas_ativas=totais[area],
            itens=tuple(sorted(por_area[area], key=lambda c: (-c.vagas, c.rotulo))[:limite]),
        ))
        for area in areas
    ]
