"""Construtores de vagas no modelo historico para os testes da API.

Modulo comum (nao conftest) para os testes importarem os construtores; o
fixture `seed` fica em tests/api/conftest.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

from api.models import JobRecord, JobSnapshot

COLETA_ANTIGA = datetime(2026, 9, 10, 9, 5, tzinfo=timezone.utc)
COLETA_ATUAL = datetime(2026, 9, 14, 9, 5, tzinfo=timezone.utc)


def vaga(source, external_id, *, ativa=True, snapshots, url=None):
    """Uma vaga unica com seus snapshots, do mais antigo ao mais recente."""
    primeira = min(s.collected_at for s in snapshots)
    ultima = max(s.collected_at for s in snapshots)
    return JobRecord(
        source=source, external_id=external_id,
        url=url or f"https://exemplo.test/{external_id}",
        first_seen_at=primeira, last_seen_at=ultima, is_active=ativa,
        closed_at=None if ativa else COLETA_ATUAL,
        snapshots=snapshots,
    )


def snapshot(title, area, *, collected_at=COLETA_ATUAL, tecnologias=(), **campos):
    return JobSnapshot(
        collected_at=collected_at, title=title, area=area,
        content_hash=f"{title}-{collected_at:%Y%m%d}", tecnologias=list(tecnologias),
        **campos,
    )
