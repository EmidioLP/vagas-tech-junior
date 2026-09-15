import sys
from pathlib import Path

import pytest

# Permite rodar `pytest` a partir da raiz do projeto sem instalar o pacote.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper import config  # noqa: E402


@pytest.fixture(autouse=True)
def _sem_banco_da_maquina(monkeypatch):
    """Nenhum teste le a DATABASE_URL do shell nem o .env.local/.env reais.

    Sem isso, um .env.local gerado pelo Neon faria os testes apontarem para o
    banco remoto.
    """
    monkeypatch.setattr(config, "ARQUIVOS_ENV", ())
    monkeypatch.delenv("DATABASE_URL", raising=False)
