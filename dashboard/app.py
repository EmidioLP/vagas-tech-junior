"""Dashboard Streamlit somente leitura.

    streamlit run dashboard/app.py

Nao coleta, nao transforma e nao grava: so le `jobs` e `collection_runs` por
`dashboard/consultas.py`. Veja dashboard/README.md.
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


def carregar_resumo() -> consultas.ResumoGeral:
    try:
        return _resumo()
    except ConfiguracaoError as exc:
        # A mensagem de ConfiguracaoError nunca traz a URL, mas a tela nao precisa dela.
        raise consultas.DadosIndisponiveis("Banco não configurado (ConfiguracaoError).") from exc


def _overview() -> None:
    paginas.overview(carregar_resumo)


st.set_page_config(page_title="Vagas Tech Júnior", page_icon="📊", layout="wide")

with st.sidebar:
    if st.button("Atualizar dados"):
        st.cache_data.clear()

navegacao = st.navigation([
    st.Page(_overview, title="Overview", url_path="overview", default=True),
    st.Page(paginas.em_construcao("Tecnologias", "etapa 08"),
            title="Tecnologias", url_path="tecnologias"),
    st.Page(paginas.em_construcao("Histórico", "etapa 08"),
            title="Histórico", url_path="historico"),
    st.Page(paginas.em_construcao("Vagas", "etapa 12"),
            title="Vagas", url_path="vagas"),
])
navegacao.run()
