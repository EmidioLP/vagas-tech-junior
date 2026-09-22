"""Inferencia da modalidade pelo texto, para os portais que nao a informam.

As armadilhas testadas aqui vieram de vagas reais: "suporte remoto" e
"atendimento presencial" sao atividades, "auxilio home office" e beneficio de
vaga hibrida, e "cloud, on premises e hibrido" e infraestrutura.
"""

import pytest

from scraper.models import Job
from scraper.modalidade import completar_modalidade, inferir_modalidade, sem_modalidade


@pytest.mark.parametrize(
    "descricao,esperado",
    [
        ("Modelo de trabalho: 100% remoto.", "Remoto"),
        ("Vaga remota para todo o Brasil.", "Remoto"),
        ("Regime de trabalho presencial em Barueri.", "Presencial"),
        ("Atuação presencial no escritório de Curitiba.", "Presencial"),
        ("Modelo híbrido, 3 dias no escritório.", "Híbrido"),
        ("Trabalho Híbrido em São Paulo.", "Híbrido"),
        ("Nenhuma pista aqui.", "Não informado"),
        ("", "Não informado"),
    ],
)
def test_frases_de_modalidade_na_descricao(descricao, esperado):
    assert inferir_modalidade("Desenvolvedor Júnior", descricao) == esperado


@pytest.mark.parametrize(
    "descricao",
    [
        "Prestar suporte remoto aos usuários.",
        "Realizar atendimento presencial aos clientes.",
        "Benefícios: auxílio home office e vale refeição.",
        "Projetos em ambientes cloud, on premises e híbrido.",
        "Experiência com nuvem híbrida (AWS e Azure).",
        "Acesso remoto a servidores.",
    ],
)
def test_armadilhas_nao_viram_modalidade(descricao):
    assert inferir_modalidade("Analista de Suporte Jr", descricao) == "Não informado"


def test_hibrido_com_dias_presenciais_e_hibrido():
    texto = "Modelo híbrido, com 1 dia por semana de atuação presencial no escritório."
    assert inferir_modalidade("Dev Jr", texto) == "Híbrido"


@pytest.mark.parametrize(
    "descricao",
    [
        # A empresa cita duas modalidades: nao ha como saber a da vaga.
        "Nosso time de tecnologia atua 100% remoto e os demais times em modelo híbrido.",
        "Trabalho remoto ou híbrido, à escolha.",
        "Trabalho remoto no primeiro mês, depois trabalho presencial.",
    ],
)
def test_modalidades_conflitantes_nao_viram_chute(descricao):
    assert inferir_modalidade("Dev Jr", descricao) == "Não informado"


def test_titulo_decide_antes_da_descricao():
    # A descricao fala do beneficio da empresa; o titulo diz a modalidade da vaga.
    titulo = "Estágio em TI (Presencial)"
    descricao = "Modelo de trabalho híbrido para os escritórios corporativos."
    assert inferir_modalidade(titulo, descricao) == "Presencial"


@pytest.mark.parametrize(
    "titulo,local,esperado",
    [
        ("Desenvolvedor Júnior - Remoto", "", "Remoto"),
        ("Jovem Aprendiz (Tecnologia) I Hibrido - BH", "", "Híbrido"),
        ("Dev Jr", "São Paulo, SP (Híbrido)", "Híbrido"),
        ("Dev Jr", "Brasil (Remote)", "Remoto"),
        ("Analista de Suporte Remoto Jr", "", "Não informado"),
    ],
)
def test_palavra_solta_vale_no_titulo_e_no_local(titulo, local, esperado):
    assert inferir_modalidade(titulo, "", local) == esperado


def test_palavra_solta_nao_vale_na_descricao():
    assert inferir_modalidade("Dev Jr", "Você será remoto? Não sabemos.") == "Não informado"


@pytest.mark.parametrize("valor,ausente", [
    ("", True), (None, True), ("Não informado", True), ("Remoto", False),
])
def test_sem_modalidade(valor, ausente):
    assert sem_modalidade(valor) is ausente


def test_completar_nunca_sobrescreve_a_modalidade_do_portal():
    job = Job(source="gupy", external_id="1", title="Dev Jr",
              description="Modelo de trabalho 100% remoto.", workplace_type="Presencial")
    assert completar_modalidade([job])[0].workplace_type == "Presencial"


def test_completar_preenche_so_o_que_falta():
    sem = Job(source="linkedin", external_id="1", title="Dev Jr",
              description="Modelo híbrido em Recife.", workplace_type="Não informado")
    vazia = Job(source="vagas", external_id="2", title="Dev Jr", description="Nada.")
    completar_modalidade([sem, vazia])
    assert sem.workplace_type == "Híbrido"
    assert vazia.workplace_type == "Não informado"
