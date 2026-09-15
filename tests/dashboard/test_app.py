"""Smoke test do app Streamlit: Overview com dados, vazia, com erro, e paginas futuras.

O banco e substituido: `config.criar_engine` e `consultas.resumo_geral` sao
trocados por fakes, e o cache do Streamlit e limpo entre os testes.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

st = pytest.importorskip("streamlit")
pytest.importorskip("sqlalchemy")

from streamlit.testing.v1 import AppTest  # noqa: E402

from dashboard import config, consultas  # noqa: E402
from scraper.config import PROJECT_ROOT, ConfiguracaoError  # noqa: E402

APP = PROJECT_ROOT / "dashboard" / "app.py"

COM_DADOS = consultas.ResumoGeral(
    ultima_coleta=consultas.Coleta(datetime(2026, 9, 15, 9, 5, tzinfo=timezone.utc), "success", 597),
    proxima_coleta=date(2026, 9, 17),
    ultima_execucao=consultas.Execucao(
        datetime(2026, 9, 16, 9, 2, tzinfo=timezone.utc), "skipped", "schedule"),
    vagas_ativas=1234,
)


@pytest.fixture(autouse=True)
def _sem_banco_real(monkeypatch):
    monkeypatch.setattr(config, "criar_engine", lambda destino=None: object())
    st.cache_data.clear()
    st.cache_resource.clear()
    yield
    st.cache_data.clear()
    st.cache_resource.clear()


def _rodar(monkeypatch, resumo=None, erro=None) -> AppTest:
    def _resumo_geral(_engine):
        if erro is not None:
            raise erro
        return resumo

    monkeypatch.setattr(consultas, "resumo_geral", _resumo_geral)
    return AppTest.from_file(APP, default_timeout=30).run()


def _textos(app: AppTest) -> str:
    elementos = [*app.title, *app.markdown, *app.caption, *app.info, *app.warning]
    return " ".join(str(e.value) for e in elementos)


def test_overview_mostra_vagas_ativas_ultima_coleta_e_agenda(monkeypatch):
    app = _rodar(monkeypatch, COM_DADOS)

    assert not app.exception
    metricas = {m.label: m.value for m in app.metric}
    assert metricas == {"Vagas ativas": "1.234", "Última coleta": "15/09/2026 às 06:05"}
    textos = _textos(app)
    assert "Vagas Tech Júnior" in textos
    assert "Última coleta: dia 15/09/2026 e próxima: dia 17/09/2026" in textos
    assert "Última execução: pulada (agendada) em 16/09/2026 às 06:02." in textos


def test_sem_coleta_mostra_estado_vazio(monkeypatch):
    app = _rodar(monkeypatch, consultas.ResumoGeral(None, None, None, 0))

    assert not app.exception
    assert not app.metric
    assert "Ainda não há coleta registrada" in app.info[0].value


def test_banco_indisponivel_mostra_aviso_sem_detalhes(monkeypatch):
    app = _rodar(monkeypatch,
                 erro=consultas.DadosIndisponiveis("Não foi possível ler o banco (OperationalError)."))

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


@pytest.mark.parametrize("titulo, etapa", [
    ("Tecnologias", "etapa 08"),
    ("Histórico", "etapa 08"),
    ("Vagas", "etapa 12"),
])
def test_paginas_futuras_mostram_em_construcao(titulo, etapa):
    # ascii(): o AppTest grava o script na codificacao padrao do sistema (cp1252 no
    # Windows) e le de volta como UTF-8; acentos no codigo-fonte quebrariam a leitura.
    app = AppTest.from_string(
        f"from dashboard import paginas\npaginas.em_construcao({ascii(titulo)}, {ascii(etapa)})()\n"
    ).run()

    assert not app.exception
    assert app.title[0].value == titulo
    assert app.info[0].value.startswith("Em construção")
    assert etapa in app.info[0].value
    assert not app.metric


def test_app_registra_as_quatro_paginas():
    fonte = APP.read_text(encoding="utf-8")
    for url_path in ("overview", "tecnologias", "historico", "vagas"):
        assert f'url_path="{url_path}"' in fonte
