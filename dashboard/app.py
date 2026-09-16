"""Dashboard Streamlit somente leitura.

    streamlit run dashboard/app.py

Nao coleta, nao transforma e nao grava: so le `jobs`, `job_snapshots` e
`collection_runs` por `dashboard/consultas.py`. Veja dashboard/README.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

# `streamlit run` coloca so a pasta do script no sys.path; o dashboard importa
# `api` e `scraper` da raiz do projeto.
RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import streamlit as st  # noqa: E402

from dashboard import config, consultas, paginas  # noqa: E402
from scraper.config import ConfiguracaoError  # noqa: E402


@st.cache_resource(show_spinner=False)
def _engine():
    return config.criar_engine()


@st.cache_data(ttl=config.TTL_SEGUNDOS, show_spinner="Carregando dados...")
def _resumo() -> consultas.ResumoGeral:
    return consultas.resumo_geral(_engine())


@st.cache_data(ttl=config.TTL_SEGUNDOS, show_spinner=False)
def _opcoes() -> consultas.OpcoesFiltro:
    return consultas.opcoes_filtro(_engine())


@st.cache_data(ttl=config.TTL_SEGUNDOS, show_spinner="Carregando dados...")
def _indicadores(filtros: consultas.Filtros) -> consultas.Indicadores:
    return consultas.indicadores_atuais(_engine(), filtros)


@st.cache_data(ttl=config.TTL_SEGUNDOS, show_spinner=False)
def _distribuicao(filtros: consultas.Filtros, dimensao: str) -> list[consultas.Contagem]:
    return consultas.distribuicao(_engine(), filtros, dimensao)


@st.cache_data(ttl=config.TTL_SEGUNDOS, show_spinner="Carregando dados...")
def _serie(filtros: consultas.Filtros) -> list[consultas.PontoSerie]:
    return consultas.serie_historica(_engine(), filtros)


@st.cache_data(ttl=config.TTL_SEGUNDOS, show_spinner="Carregando dados...")
def _vagas(filtros: consultas.Filtros, somente_ativas: bool, pagina: int) -> consultas.PaginaVagas:
    return consultas.listar_vagas(_engine(), filtros, somente_ativas, pagina,
                                  paginas.VAGAS_POR_PAGINA)


@st.cache_data(ttl=config.TTL_SEGUNDOS, show_spinner="Carregando dados...")
def _tecnologias(filtros: consultas.Filtros) -> consultas.RankingTecnologias:
    return consultas.top_tecnologias(_engine(), filtros)


def _protegida(consulta):
    """Sem banco configurado, a pagina mostra o mesmo aviso de banco inacessivel."""

    def _chamar(*args):
        try:
            return consulta(*args)
        except ConfiguracaoError as exc:
            # A mensagem de ConfiguracaoError nunca traz a URL, mas a tela nao precisa dela.
            raise consultas.DadosIndisponiveis("Banco não configurado (ConfiguracaoError).") from exc

    return _chamar


DADOS = paginas.Dados(
    resumo=_protegida(_resumo),
    opcoes=_protegida(_opcoes),
    indicadores=_protegida(_indicadores),
    distribuicao=_protegida(_distribuicao),
    serie=_protegida(_serie),
    vagas=_protegida(_vagas),
    tecnologias=_protegida(_tecnologias),
)


def _overview() -> None:
    paginas.overview(DADOS)


def _tecnologias_pagina() -> None:
    paginas.tecnologias(DADOS)


def _historico() -> None:
    paginas.historico(DADOS)


def _vagas_pagina() -> None:
    paginas.vagas(DADOS)


st.set_page_config(page_title="Vagas Tech Júnior", page_icon="📊", layout="wide")

# O Streamlit descarta o estado de um widget que nao foi desenhado nesta execucao.
# Regravar as chaves mantem os filtros ao passar por uma pagina que nao usa todos.
for chave in paginas.CHAVES_FILTRO:
    if chave in st.session_state:
        st.session_state[chave] = st.session_state[chave]

with st.sidebar:
    if st.button("Atualizar dados"):
        st.cache_data.clear()

navegacao = st.navigation([
    st.Page(_overview, title="Overview", url_path="overview", default=True),
    st.Page(_tecnologias_pagina, title="Tecnologias", url_path="tecnologias"),
    st.Page(_historico, title="Histórico", url_path="historico"),
    st.Page(_vagas_pagina, title="Vagas", url_path="vagas"),
])
navegacao.run()
