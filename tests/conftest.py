import sys
from pathlib import Path

import pytest

# Permite rodar `pytest` a partir da raiz do projeto sem instalar o pacote.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper import config  # noqa: E402


@pytest.fixture(autouse=True)
def _sem_banco_da_maquina(monkeypatch):
    """Nenhum teste le a DATABASE_URL (nem o intervalo de coleta) do shell nem o
    .env.local/.env reais.

    Sem isso, um .env.local gerado pelo Neon faria os testes apontarem para o
    banco remoto.
    """
    monkeypatch.setattr(config, "ARQUIVOS_ENV", ())
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL_UNPOOLED", raising=False)
    monkeypatch.delenv("COLLECTION_INTERVAL_DAYS", raising=False)
    monkeypatch.delenv("DASHBOARD_DB", raising=False)


@pytest.fixture
def banco_historico(tmp_path):
    """Arquivo SQLite com `alembic upgrade head`: o schema das migrations, nao o do create_all.

    Fica na raiz de `tests/` porque persistencia (tests/api) e dashboard
    (tests/dashboard) testam contra o mesmo schema.
    """
    pytest.importorskip("alembic", reason="Alembic não instalado; testes com banco migrado pulados.")
    from alembic import command
    from alembic.config import Config

    caminho = tmp_path / "historico.db"
    cfg = Config(str(config.PROJECT_ROOT / "alembic.ini"))
    cfg.attributes["database_url"] = f"sqlite:///{caminho.as_posix()}"
    command.upgrade(cfg, "head")
    return caminho
