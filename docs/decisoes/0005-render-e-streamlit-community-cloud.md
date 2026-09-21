# ADR 0005 — API no Render e dashboard no Streamlit Community Cloud

- **Status:** aceito
- **Data:** 16/09/2026 (API publicada antes da plataforma de dados; dashboard na
  etapa 07)

## Contexto

A API e o dashboard só leem o banco. O tráfego é de portfólio: poucos acessos,
concentrados em dias específicos. O orçamento é zero, e ninguém opera servidor.
O scraper não pode rodar junto, porque portais de vaga bloqueiam IP de nuvem.

## Decisão

- **API (FastAPI) no Render**, plano free, a partir de `render.yaml`: o build
  instala `requirements-api.txt` (sem matplotlib), o `startCommand` só sobe o
  uvicorn e `healthCheckPath` é `/health`. `DATABASE_URL` declarada com
  `sync: false`, com o valor só no painel. Nada de migration nem de seed no boot.
- **Dashboard (Streamlit) no Community Cloud**, publicado manualmente pelo painel,
  entrypoint `dashboard/app.py`, dependências `requirements-dashboard.txt`, lendo a
  `dados-main` com o papel `dashboard_leitura` (só `SELECT` + transação read-only).
- Os dois leem a mesma `dados-main` pela mesma regra de estado atual.

Detalhes: [`../api.md`](../api.md#deploy), [`../deploy.md`](../deploy.md).

## Consequências

- **Ganha:** custo zero, deploy a partir do repositório, URLs públicas
  verificáveis e dependências enxutas por serviço. `tests/test_render_yaml.py` e
  `tests/test_deploy_dashboard.py` fixam a configuração.
- **Custa:**
  - **hibernação:** a API dorme após 15 minutos sem uso, e o primeiro acesso leva
    cerca de 1 minuto. O dashboard dorme após alguns dias e mostra um botão para acordar;
  - o deploy do dashboard e as variáveis dos dois serviços são manuais, fora do git;
  - recursos limitados (cerca de 1 GB de memória no Streamlit), e o histórico é
    carregado em memória. Medido depois: o gargalo é o tempo de montar a série, não
    a memória ([0007](0007-serie-historica-em-python.md));
  - dois fornecedores a mais, além do Neon e do GitHub. Nenhum deles tem SLA no
    plano gratuito.

## O que mudaria a decisão

- Uso real que não tolere o *cold start* ou a hibernação.
- Necessidade de autenticação, escrita ou limites de taxa por cliente.
- Dashboard com consultas que não caibam na memória do plano gratuito.
