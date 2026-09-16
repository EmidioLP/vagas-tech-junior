"""Smoke test do app Streamlit: as quatro paginas com dados, vazias e com erro.

- `app.py` inteiro roda com `config.criar_engine` e as consultas trocadas por
  fakes (so a Overview, que e a pagina padrao, aparece no AppTest);
- cada pagina roda sozinha com um `Dados` falso ou com as consultas reais sobre o
  banco de teste (cenario em cenario_historico.py).

O cache do Streamlit e limpo entre os testes.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

st = pytest.importorskip("streamlit")
pytest.importorskip("sqlalchemy")

from streamlit.testing.v1 import AppTest  # noqa: E402

from dashboard import config, consultas, paginas  # noqa: E402
from dashboard.consultas import Contagem, PontoSerie  # noqa: E402
from scraper.config import PROJECT_ROOT, ConfiguracaoError  # noqa: E402

from cenario_historico import D1, D2, D3  # noqa: E402

APP = PROJECT_ROOT / "dashboard" / "app.py"

COM_DADOS = consultas.ResumoGeral(
    ultima_coleta=consultas.Coleta(datetime(2026, 9, 15, 9, 5, tzinfo=timezone.utc), "success", 597),
    proxima_coleta=date(2026, 9, 17),
    ultima_execucao=consultas.Execucao(
        datetime(2026, 9, 16, 9, 2, tzinfo=timezone.utc), "skipped", "schedule"),
    vagas_ativas=1234,
)
VAZIO = consultas.ResumoGeral(None, None, None, 0)
OPCOES = consultas.OpcoesFiltro(("gupy", "vagas"), ("Backend", "Data"),
                                ("Remoto", "Não informado"), D1, D3)
SEM_COLETA = consultas.OpcoesFiltro((), (), (), None, None)
INDICADORES = consultas.Indicadores(vagas_ativas=1234, empresas=456, remotas=617,
                                    sem_modalidade=100, fontes=6)
DISTRIBUICAO = [Contagem("Backend", 800), Contagem("Data", 434)]
SERIE = [
    PontoSerie(D1, 10, 10, 10, {"Backend": 6, "Data": 4}),
    PontoSerie(D2, 12, 3, 5, {"Backend": 7, "Data": 5}),
]
RANKING = consultas.RankingTecnologias(base=40, vagas_ativas=50,
                                       itens=(Contagem("SQL", 20), Contagem("Python", 10)))
ERRO = consultas.DadosIndisponiveis("Não foi possível ler o banco (OperationalError).")


@pytest.fixture(autouse=True)
def _sem_banco_real(monkeypatch):
    monkeypatch.setattr(config, "criar_engine", lambda destino=None: object())
    st.cache_data.clear()
    st.cache_resource.clear()
    yield
    st.cache_data.clear()
    st.cache_resource.clear()


def _falha(*_args):
    raise ERRO


def _dados(**trocas) -> paginas.Dados:
    valores = dict(
        resumo=lambda: COM_DADOS,
        opcoes=lambda: OPCOES,
        indicadores=lambda filtros: INDICADORES,
        distribuicao=lambda filtros, dimensao: DISTRIBUICAO,
        serie=lambda filtros: SERIE,
        vagas=lambda filtros, somente_ativas, pagina: consultas.PaginaVagas((), 0, pagina, 50),
        tecnologias=lambda filtros: RANKING,
    )
    valores.update(trocas)
    return paginas.Dados(**valores)


def _pagina(nome, dados):
    from dashboard import paginas

    getattr(paginas, nome)(dados)


def _rodar_pagina(nome: str, dados: paginas.Dados) -> AppTest:
    return AppTest.from_function(_pagina, args=(nome, dados), default_timeout=30).run()


def _rodar_app(monkeypatch, resumo=COM_DADOS, erro=None) -> AppTest:
    def _resumo_geral(_engine):
        if erro is not None:
            raise erro
        return resumo

    monkeypatch.setattr(consultas, "resumo_geral", _resumo_geral)
    monkeypatch.setattr(consultas, "opcoes_filtro", lambda _engine: OPCOES)
    monkeypatch.setattr(consultas, "indicadores_atuais", lambda _engine, _f: INDICADORES)
    monkeypatch.setattr(consultas, "distribuicao", lambda _engine, _f, _d: DISTRIBUICAO)
    return AppTest.from_file(APP, default_timeout=30).run()


def _textos(app: AppTest) -> str:
    elementos = [*app.title, *app.header, *app.subheader, *app.markdown, *app.caption,
                 *app.info, *app.warning]
    return " ".join(str(e.value) for e in elementos)


# --- app inteiro ---------------------------------------------------------------


def test_overview_mostra_ultima_coleta_agenda_e_kpis(monkeypatch):
    app = _rodar_app(monkeypatch)

    assert not app.exception
    metricas = {m.label: m.value for m in app.metric}
    assert metricas == {
        "Última coleta": "15/09/2026 às 06:05",
        "Vagas ativas": "1.234",
        "Empresas": "456",
        "Remoto": "50,0%",
        "Fontes": "6",
    }
    textos = _textos(app)
    assert "Vagas Tech Júnior" in textos
    assert "Última coleta: dia 15/09/2026 e próxima: dia 17/09/2026" in textos
    assert "Última execução: pulada (agendada) em 16/09/2026 às 06:02." in textos
    assert "Vagas únicas ativas agora" in textos
    assert "não de snapshots" in textos
    # Cada KPI explica o que conta.
    assert all(m.help for m in app.metric if m.label != "Última coleta")


def test_overview_filtros_na_barra_lateral_sem_periodo(monkeypatch):
    app = _rodar_app(monkeypatch)

    assert [m.label for m in app.sidebar.multiselect] == ["Fonte", "Área", "Modalidade"]
    assert not app.sidebar.date_input
    assert "fotografia atual" in " ".join(c.value for c in app.sidebar.caption)


def test_filtro_escolhido_chega_na_consulta(monkeypatch):
    recebidos = []
    app = _rodar_app(monkeypatch)
    monkeypatch.setattr(consultas, "indicadores_atuais",
                        lambda _engine, filtros: recebidos.append(filtros) or INDICADORES)

    app.sidebar.multiselect[0].select("vagas").run()

    assert not app.exception
    assert recebidos[-1] == consultas.Filtros(fontes=("vagas",))


def test_sem_coleta_mostra_estado_vazio(monkeypatch):
    app = _rodar_app(monkeypatch, VAZIO)

    assert not app.exception
    assert not app.metric
    assert "Ainda não há coleta registrada" in app.info[0].value


def test_banco_indisponivel_mostra_aviso_sem_detalhes(monkeypatch):
    app = _rodar_app(monkeypatch, erro=ERRO)

    assert not app.exception
    assert "Dados indisponíveis no momento" in app.warning[0].value
    textos = _textos(app)
    assert "://" not in textos
    assert "senha" not in textos


def test_sem_configuracao_de_banco_mostra_o_mesmo_aviso(monkeypatch):
    def _sem_url(destino=None):
        raise ConfiguracaoError("DATABASE_URL não definida.")

    monkeypatch.setattr(config, "criar_engine", _sem_url)
    app = AppTest.from_file(APP, default_timeout=30).run()

    assert not app.exception
    assert "Dados indisponíveis no momento" in app.warning[0].value
    assert "ConfiguracaoError" in _textos(app)


def test_app_registra_as_quatro_paginas_sem_placeholder():
    fonte = APP.read_text(encoding="utf-8")
    for url_path in ("overview", "tecnologias", "historico", "vagas"):
        assert f'url_path="{url_path}"' in fonte
    assert "em_construcao" not in fonte


# --- Overview ------------------------------------------------------------------


def test_overview_filtro_sem_vagas_mostra_estado_vazio():
    vazio = consultas.Indicadores(0, 0, 0, 0, 0)
    app = _rodar_pagina("overview", _dados(indicadores=lambda filtros: vazio))

    assert not app.exception
    assert [m.label for m in app.metric] == ["Última coleta"]
    assert "Nenhuma vaga ativa com esses filtros" in _textos(app)


# --- Histórico ---------------------------------------------------------------------


def test_historico_com_serie_mostra_graficos_e_legenda():
    app = _rodar_pagina("historico", _dados())

    assert not app.exception
    textos = _textos(app)
    for titulo in ("Vagas abertas (únicas)", "Vagas abertas por área (únicas)",
                   "Vagas novas (únicas)", "Snapshots gravados"):
        assert titulo in textos
    assert "Mudanças de estado observadas no dia. Não são vagas." in textos
    assert app.expander[0].label == "Como ler estes números"
    assert "snapshots por dia contam mudanças, não vagas vistas" in textos
    assert app.sidebar.date_input[0].value == (D1, D3)


def test_historico_periodo_sem_coleta_nao_desenha_grafico():
    app = _rodar_pagina("historico", _dados(serie=lambda filtros: []))

    assert not app.exception
    assert "Nenhuma coleta no período selecionado. Há coletas de 10/09/2026 a 14/09/2026." in _textos(app)
    assert not app.metric
    assert "Vagas abertas (únicas)" not in _textos(app)


def test_historico_um_dia_mostra_numeros_e_nao_tendencia():
    app = _rodar_pagina("historico", _dados(serie=lambda filtros: SERIE[:1]))

    assert not app.exception
    assert "uma tendência precisa de pelo menos dois" in _textos(app)
    assert {m.label: m.value for m in app.metric} == {
        "Vagas abertas (únicas)": "10", "Vagas novas (únicas)": "10", "Snapshots gravados": "10"}


def test_historico_filtro_que_zera_tudo_explica():
    zerada = [PontoSerie(D1, 0, 0, 0, {}), PontoSerie(D2, 0, 0, 0, {})]
    app = _rodar_pagina("historico", _dados(serie=lambda filtros: zerada))

    assert not app.exception
    assert "nenhuma vaga com esses filtros" in _textos(app)


def test_historico_sem_nenhuma_coleta():
    app = _rodar_pagina("historico", _dados(opcoes=lambda: SEM_COLETA, serie=lambda filtros: []))

    assert not app.exception
    assert not app.sidebar.date_input
    assert "Ainda não há coleta registrada." in _textos(app)


# --- Vagas ---------------------------------------------------------------------------


def test_vagas_mostra_tabela_paginada_com_link_seguro():
    linha = consultas.LinhaVaga(
        "Dev Jr", "Acme", "Backend", "Remoto", "gupy",
        datetime(2026, 9, 10, 9, 5, tzinfo=timezone.utc),
        datetime(2026, 9, 14, 9, 5, tzinfo=timezone.utc), True, "https://portal.exemplo/1")
    pagina = consultas.PaginaVagas((linha,), total=120, pagina=1, por_pagina=50)
    app = _rodar_pagina("vagas", _dados(vagas=lambda f, a, p: pagina))

    assert not app.exception
    tabela = app.dataframe[0].value
    assert list(tabela.columns) == ["Título", "Empresa", "Área", "Modalidade", "Fonte", "Ativa",
                                    "Primeiro avistamento", "Último avistamento", "Link"]
    assert tabela.iloc[0]["Link"] == "https://portal.exemplo/1"
    assert "120 vagas únicas · página 1 de 3" in _textos(app)
    assert app.sidebar.toggle[0].value is True


def test_vagas_sem_resultado_mostra_estado_vazio():
    app = _rodar_pagina("vagas", _dados())

    assert not app.exception
    assert not app.dataframe
    assert "Nenhuma vaga com esses filtros no período" in _textos(app)


def test_vagas_pagina_alem_do_fim():
    alem = consultas.PaginaVagas((), total=120, pagina=9, por_pagina=50)
    app = _rodar_pagina("vagas", _dados(vagas=lambda f, a, p: alem))

    assert not app.exception
    assert "passou do fim: há 3 páginas" in _textos(app)


# --- Tecnologias ---------------------------------------------------------------------


def test_tecnologias_declara_a_base_e_a_ressalva():
    app = _rodar_pagina("tecnologias", _dados())

    assert not app.exception
    textos = _textos(app)
    assert "Base: 40 das 50 vagas ativas citam alguma tecnologia" in textos
    assert "menção, não exigência" in textos


def test_tecnologias_base_pequena_nao_mostra_ranking():
    pequeno = consultas.RankingTecnologias(base=5, vagas_ativas=50, itens=(Contagem("SQL", 5),))
    app = _rodar_pagina("tecnologias", _dados(tecnologias=lambda filtros: pequeno))

    assert not app.exception
    textos = _textos(app)
    assert "Só 5 vagas ativas neste recorte citam alguma tecnologia" in textos
    assert "Base:" not in textos


# --- todas as paginas ------------------------------------------------------------------


@pytest.mark.parametrize("nome", ["overview", "historico", "vagas", "tecnologias"])
def test_pagina_com_banco_indisponivel_mostra_aviso(nome):
    dados = _dados(resumo=_falha, opcoes=_falha, indicadores=_falha, distribuicao=_falha,
                   serie=_falha, vagas=_falha, tecnologias=_falha)
    app = _rodar_pagina(nome, dados)

    assert not app.exception
    assert "Dados indisponíveis no momento" in app.warning[0].value
    assert "://" not in _textos(app)


@pytest.mark.parametrize("nome", ["overview", "historico", "vagas", "tecnologias"])
def test_pagina_com_consultas_reais_no_banco_de_teste(nome, banco_com_historico, monkeypatch):
    monkeypatch.undo()  # volta o criar_engine real
    engine = config.criar_engine(banco_com_historico)
    dados = paginas.Dados(
        resumo=lambda: consultas.resumo_geral(engine),
        opcoes=lambda: consultas.opcoes_filtro(engine),
        indicadores=lambda f: consultas.indicadores_atuais(engine, f),
        distribuicao=lambda f, d: consultas.distribuicao(engine, f, d),
        serie=lambda f: consultas.serie_historica(engine, f),
        vagas=lambda f, a, p: consultas.listar_vagas(engine, f, a, p),
        tecnologias=lambda f: consultas.top_tecnologias(engine, f),
    )
    try:
        app = _rodar_pagina(nome, dados)
    finally:
        engine.dispose()

    assert not app.exception
    assert not app.warning
