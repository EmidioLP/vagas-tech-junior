import pytest

from scraper.dedupe import deduplicate, identidade_no_link
from scraper.models import Job


def test_remove_mesma_vaga_do_mesmo_portal():
    jobs = [
        Job(source="gupy", external_id="1", title="Dev Júnior", company="ACME"),
        Job(source="gupy", external_id="1", title="Dev Júnior", company="ACME"),
    ]
    unique, removed = deduplicate(jobs)
    assert len(unique) == 1
    assert removed == 1


def test_mantem_a_versao_com_descricao_mais_longa():
    jobs = [
        Job(source="gupy", external_id="1", title="Dev Júnior",
            company="ACME", description="curta"),
        Job(source="gupy", external_id="1", title="Dev Júnior",
            company="ACME", description="uma descricao bem mais longa da vaga"),
    ]
    unique, _ = deduplicate(jobs)
    assert unique[0].description == "uma descricao bem mais longa da vaga"


def test_cruza_portais_por_titulo_e_empresa():
    jobs = [
        Job(source="gupy", external_id="1", title="Desenvolvedor Júnior", company="ACME"),
        Job(source="vagas", external_id="99", title="desenvolvedor junior", company="Acme"),
    ]
    unique, removed = deduplicate(jobs)
    assert len(unique) == 1
    assert removed == 1


def test_nao_cruza_vagas_de_empresas_diferentes():
    jobs = [
        Job(source="gupy", external_id="1", title="Desenvolvedor Júnior", company="ACME"),
        Job(source="gupy", external_id="2", title="Desenvolvedor Júnior", company="Globex"),
    ]
    unique, removed = deduplicate(jobs)
    assert len(unique) == 2
    assert removed == 0


def test_vagas_sem_empresa_nao_sao_agrupadas():
    jobs = [
        Job(source="gupy", external_id="1", title="Desenvolvedor Júnior", company=""),
        Job(source="gupy", external_id="2", title="Desenvolvedor Júnior", company=""),
    ]
    unique, removed = deduplicate(jobs)
    assert len(unique) == 2
    assert removed == 0


def test_funde_mesma_vaga_com_nome_de_empresa_diferente():
    """Casos reais: a Gupy escreve o nome completo, o LinkedIn o curto."""
    jobs = [
        Job(source="gupy", external_id="1", title="Desenvolvedor Fullstack Jr",
            company="Minsait an Indra Company", description="descricao longa"),
        Job(source="linkedin", external_id="9", title="Desenvolvedor Fullstack Jr",
            company="Minsait"),
    ]
    unique, removed = deduplicate(jobs)
    assert len(unique) == 1 and removed == 1
    # Fica a versão com mais informação.
    assert unique[0].description == "descricao longa"


def test_funde_quando_o_nome_curto_esta_contido_no_longo():
    jobs = [
        Job(source="gupy", external_id="1", title="Analista de Sistemas Júnior",
            company="Centro Universitário FEI"),
        Job(source="linkedin", external_id="9", title="Analista de Sistemas Júnior",
            company="FEI"),
    ]
    assert len(deduplicate(jobs)[0]) == 1


def test_titulo_generico_em_empresas_diferentes_nao_funde():
    """'Analista de Sistemas Júnior' existe em dezenas de empresas."""
    jobs = [
        Job(source="gupy", external_id="1", title="Analista de Sistemas Júnior",
            company="Techne"),
        Job(source="linkedin", external_id="9", title="Analista de Sistemas Júnior",
            company="Globoaves"),
    ]
    unique, removed = deduplicate(jobs)
    assert len(unique) == 2 and removed == 0


def test_confidencial_nao_identifica_empresa():
    """Duas vagas confidenciais com o mesmo título não são a mesma vaga."""
    jobs = [
        Job(source="gupy", external_id="1", title="Analista Júnior de TI",
            company="Confidencial"),
        Job(source="vagas", external_id="9", title="Analista Júnior de TI",
            company="Confidencial"),
    ]
    assert len(deduplicate(jobs)[0]) == 2


def test_sufixo_societario_nao_impede_a_fusao():
    jobs = [
        Job(source="gupy", external_id="1", title="Dev Júnior", company="ACME"),
        Job(source="linkedin", external_id="9", title="Dev Júnior",
            company="ACME Soluções em Tecnologia LTDA"),
    ]
    assert len(deduplicate(jobs)[0]) == 1


def test_titulos_diferentes_da_mesma_empresa_nao_fundem():
    """Duas vagas distintas na mesma empresa continuam sendo duas."""
    jobs = [
        Job(source="gupy", external_id="1", title="Desenvolvedor Júnior",
            company="ACME"),
        Job(source="linkedin", external_id="9", title="Analista de Testes Júnior",
            company="ACME"),
    ]
    assert len(deduplicate(jobs)[0]) == 2


def test_lista_vazia():
    unique, removed = deduplicate([])
    assert unique == []
    assert removed == 0


# --- id embutido no link (Passo 2) -------------------------------------------

@pytest.mark.parametrize("url,esperado", [
    ("https://agtaxtech.inhire.app/vagas/53e6e9da-81ce-4a1b-98bc-e32a77eea102",
     "uuid:53e6e9da-81ce-4a1b-98bc-e32a77eea102"),
    ("https://agtaxtech.inhire.app/vagas/53e6e9da-81ce-4a1b-98bc-e32a77eea102/dev-jr",
     "uuid:53e6e9da-81ce-4a1b-98bc-e32a77eea102"),
    ("https://jobs.quickin.io/infovagas/jobs/6a64aa2322a5d000139206bb",
     "quickin.io:6a64aa2322a5d000139206bb"),
    ("https://gruposeb.gupy.io/job/eyJqb2JJZCI6MTI0NTk3MzhpfQ==?x=1",
     "gupy.io:eyJqb2JJZCI6MTI0NTk3MzhpfQ=="),
    # Sufixo composto: sem tratar, os dois virariam "com.br".
    ("https://www.infojobs.com.br/vaga-de-auxiliar__12005412.aspx", "infojobs.com.br:12005412"),
    ("https://www.vagas.com.br/vagas/v2824782/dev-jr", "vagas.com.br:2824782"),
    # Subdominio nao atrapalha.
    ("https://br.linkedin.com/jobs/view/estagiario-de-ti-at-x-4464615185", "linkedin.com:4464615185"),
    ("https://www.linkedin.com/jobs/view/4464615185/", "linkedin.com:4464615185"),
    ("https://atracaodetalentos.totvs.app/vempratotvs/11639/tech", "totvs.app:11639"),
    ("https://empregos.recrutei.com.br/vaga/gex-corporation/158928-analista-de-atendimento",
     "recrutei.com.br:158928"),
])
def test_identidade_no_link_reconhece_o_id(url, esperado):
    assert identidade_no_link(url) == esperado


@pytest.mark.parametrize("url", [
    # Slug de titulo NAO e id: seria igual em duas empresas do mesmo portal.
    "https://www.geekhunter.com/pt/locaweb/jobs/desenvolvedor--a--junior---net--1",
    "https://vaga-ja.com/vagas/empresa-x/estagio-em-comercio-exterior",
    # O numero do fim do slug do Abler nao e o id da vaga (slug 637999, vaga 393184).
    "https://candidatos.abler.com.br/vagas/desenvolvedor-fullstack-junior-637999",
    "https://empresa.gupy.io/",
    "#",
    "",
])
def test_link_sem_id_nao_gera_chave(url):
    assert identidade_no_link(url) == ""


@pytest.mark.parametrize("url", [
    # "carreiratotvslinx" juntava 3 vagas da Linx.
    "https://carreiratotvslinx.totvs.app/carreiratotvslinx/vagas",
    # "CandidateExperience" juntava 6 vagas de empresas diferentes.
    "https://x.test/hcmUI/CandidateExperience/requisitions",
])
def test_palavra_sem_digito_nao_e_id(url):
    assert identidade_no_link(url) == ""


@pytest.mark.parametrize("url,esperado", [
    # As duas fontes exclusivas deste projeto: id de 5-6 digitos colado no slug.
    ("https://trampos.co/oportunidades/774266-estagiario-a-em-qa", "trampos.co:774266"),
    ("https://trampos.co/oportunidades/774266-estagiario-a-em-qa/share/email",
     "trampos.co:774266"),
    ("https://programathor.com.br/jobs/31809-desenvolvedor-a-php-junior",
     "programathor.com.br:31809"),
])
def test_id_antes_do_slug(url, esperado):
    assert identidade_no_link(url) == esperado


def test_ano_no_comeco_do_slug_nao_e_id():
    """Com quatro dígitos, "2026-programa-de-estagio" juntaria vagas que só
    compartilham o ano."""
    assert identidade_no_link("https://x.test/vagas/2026-programa-de-estagio") == ""


def test_numero_de_requisicao_no_titulo_nao_vence_o_id_do_linkedin():
    """Caso real da coleta: o título começa com o número de requisição da
    empresa. O id da vaga é o do fim da URL, não o "10274" do começo do slug --
    por isso a regra de dígitos longos vem antes da de id-colado-no-slug."""
    url = ("https://br.linkedin.com/jobs/view/"
           "10274-analyst-analista-de-dados-junior-presencial-at-provider-it-4454450486")
    assert identidade_no_link(url) == "linkedin.com:4454450486"


def test_os_dois_formatos_de_url_da_gupy_nao_se_fundem():
    """Limitação conhecida e aceita: a Gupy publica a mesma vaga como token
    base64 (`/job/<token>`) e como id numérico (`/jobs/<num>`), e os dois não se
    parecem. Cada um vira uma chave; nenhuma fusão falsa acontece."""
    token = identidade_no_link(
        "https://3coracoes.gupy.io/job/eyJqb2JJZCI6MTIzOTUyMzYsInNvdXJjZSI6Imd1cHlfcG9ydGFsIn0=")
    numero = identidade_no_link("https://3coracoes.gupy.io/jobs/11326629")
    assert token == "gupy.io:eyJqb2JJZCI6MTIzOTUyMzYsInNvdXJjZSI6Imd1cHlfcG9ydGFsIn0="
    assert numero == "gupy.io:11326629"
    assert token != numero


def test_mesmo_link_funde_mesmo_com_titulo_reescrito():
    """Caso real: mesma vaga da BMP, titulo reescrito pelo agregador."""
    jobs = [
        Job(source="inhire", external_id="5e4fc0bc", company="BMP",
            title="Desenvolvedor(a) Júnior – Engenharia / Projetos Técnicos",
            url="https://bmp.inhire.app/vagas/5e4fc0bc-1111-2222-3333-444455556666",
            description="descricao completa da vaga"),
        Job(source="querovagastech", external_id="99", company="BMP",
            title="DESENVOLVEDOR JÚNIOR",
            url="https://bmp.inhire.app/vagas/5e4fc0bc-1111-2222-3333-444455556666/dev-junior"),
    ]
    unique, removed = deduplicate(jobs)
    assert len(unique) == 1 and removed == 1
    assert unique[0].description == "descricao completa da vaga"


def test_link_funde_mesmo_com_empresa_escrita_de_outro_jeito():
    """Caso real da coleta: "Estágio Aurora" e "Programa de Estágios" anunciam a
    mesma vaga da Gupy. Nem o título nem a empresa casam; o link casa."""
    url = "https://aurora.gupy.io/job/eyJqb2JJZCI6MTI0Mzg0MDQsInNvdXJjZSI6Imd1cHkifQ=="
    jobs = [
        Job(source="gupy", external_id="1", company="Estágio Aurora",
            title="Estágio Superior Não Obrigatório - Tecnologia", url=url,
            description="descricao completa"),
        Job(source="querovagastech", external_id="2", company="Programa de Estágios",
            title="Estágio Superior Não Obrigatório - Tecnologia | Aurora", url=url),
    ]
    assert len(deduplicate(jobs)[0]) == 1


def test_links_diferentes_do_mesmo_portal_nao_fundem():
    jobs = [
        Job(source="linkedin", external_id="1", title="Dev Júnior", company="Acme",
            url="https://www.linkedin.com/jobs/view/4464615185"),
        Job(source="linkedin", external_id="2", title="Dev Júnior", company="Outra Empresa",
            url="https://www.linkedin.com/jobs/view/4464615186"),
    ]
    assert len(deduplicate(jobs)[0]) == 2


def test_id_numerico_igual_em_portais_diferentes_nao_funde():
    jobs = [
        Job(source="a", external_id="1", title="Dev Júnior", company="Empresa A",
            url="https://atracaodetalentos.totvs.app/vempratotvs/11639/x"),
        Job(source="b", external_id="2", title="Dev Júnior", company="Empresa B",
            url="https://prezensa.com/vagas/11639"),
    ]
    assert len(deduplicate(jobs)[0]) == 2


# --- marcas de duas letras ----------------------------------------------------

def test_marca_de_duas_letras_funde_entre_portais():
    jobs = [
        Job(source="linkedin", external_id="1", company="MV",
            title="DESENVOLVEDOR(A) JAVA FULLSTACK JÚNIOR"),
        Job(source="geekhunter", external_id="2", company="MV Saúde Digital",
            title="Desenvolvedor(a) Java Fullstack Júnior"),
    ]
    assert len(deduplicate(jobs)[0]) == 1


def test_letra_solitaria_nao_identifica_empresa():
    """"S.A." vira "s" e "a" — se contassem, toda S.A. seria a mesma empresa."""
    jobs = [
        Job(source="gupy", external_id="1", title="Dev Júnior", company="S.A."),
        Job(source="linkedin", external_id="2", title="Dev Júnior", company="S/A"),
    ]
    assert len(deduplicate(jobs)[0]) == 2


def test_sigla_generica_de_duas_letras_nao_funde_empresas():
    jobs = [
        Job(source="gupy", external_id="1", title="Analista de Suporte Jr",
            company="4INFRA Consultoria em TI"),
        Job(source="linkedin", external_id="2", title="Analista de Suporte Jr",
            company="Digitech Soluções em TI"),
    ]
    assert len(deduplicate(jobs)[0]) == 2
