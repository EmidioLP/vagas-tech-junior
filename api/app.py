"""Aplicacao FastAPI.

API somente leitura sobre o historico que o pipeline grava (`jobs` +
`job_snapshots`). Nao ha endpoints de escrita: as vagas entram pela coleta
(`python main.py`), nunca por HTTP.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from dataclasses import asdict

from fastapi import Depends, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from persistence.frescor import ESTADOS_COM_PROBLEMA, estado_das_coletas

from scraper import __version__

from .database import get_db, init_db
from .models import JobRecord
from .routers import areas, tecnologias, vagas
from .schemas import FrescorOut

DESCRIPTION = """
API de consulta das vagas júnior de tecnologia coletadas pelo scraper.

**Somente leitura.** Os dados vêm da coleta automática nos portais de vagas,
gravada no banco a cada execução (`python main.py`). Cada vaga é uma vaga única
com o estado da coleta mais recente em que apareceu, a mesma regra do dashboard.

- `/vagas` — vagas ativas, com filtros por área, tecnologia, modalidade e fonte
- `/areas` — as 10 áreas com contagem de vagas ativas
- `/tecnologias` — as tecnologias com contagem de vagas ativas que as citam
"""

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Resolve DATABASE_URL aqui: sem ela a API nao sobe, em vez de subir e
    # falhar na primeira requisicao.
    init_db()
    yield


app = FastAPI(
    title="vagas-tech-junior API",
    description=DESCRIPTION,
    version=__version__,
    contact={"name": "vagas-tech-junior"},
    lifespan=lifespan,
)

app.include_router(vagas.router)
app.include_router(areas.router)
app.include_router(tecnologias.router)


@app.exception_handler(RequestValidationError)
async def _validacao(request: Request, exc: RequestValidationError) -> JSONResponse:
    """422 com o mesmo formato `{"detail": ...}` dos erros 404."""
    erros = "; ".join(
        f"{'.'.join(str(p) for p in e['loc'][1:])}: {e['msg']}" for e in exc.errors()
    )
    return JSONResponse(
        status_code=422,
        content={"detail": f"Parâmetros inválidos. {erros}"},
    )


@app.get("/", tags=["meta"], summary="Informações da API")
def raiz() -> dict:
    return {
        "nome": "vagas-tech-junior API",
        "versao": __version__,
        "somente_leitura": True,
        "docs": "/docs",
        "endpoints": ["/vagas", "/vagas/{id}", "/areas", "/tecnologias",
                      "/health", "/health/dados"],
    }


@app.get("/health", tags=["meta"], summary="Checagem de saúde")
def health(db: Session = Depends(get_db)) -> dict:
    """Usa a mesma sessao das demais rotas, e nao um engine proprio.

    Assim a checagem enxerga exatamente o banco que a API esta atendendo --
    seja SQLite ou Postgres -- e falha junto com ela se o banco cair, que e o
    que o healthcheck do compose precisa detectar.
    """
    total = db.scalar(
        select(func.count()).select_from(JobRecord).where(JobRecord.is_active.is_(True))
    ) or 0
    return {"status": "ok", "vagas": total}


@app.get(
    "/health/dados",
    tags=["meta"],
    summary="Frescor dos dados",
    response_model=FrescorOut,
    responses={503: {"model": FrescorOut,
                     "description": "Dados vencidos, coleta parada, sem coleta ou banco indisponível."}},
)
def health_dados(db: Session = Depends(get_db)) -> JSONResponse:
    """Se os dados estão em dia. **Não** é o health check do Render.

    `/health` é liveness e responde 200 mesmo com dado velho: se respondesse erro,
    o Render reiniciaria uma API saudável. Este endpoint responde **503** quando os
    dados estão vencidos, a coleta automática parou ou não há coleta, para que um
    monitor de uptime externo alerte. Regra em `persistence/frescor.py`.
    """
    try:
        frescor = estado_das_coletas(db)
    except SQLAlchemyError as exc:
        # So o tipo do erro: a mensagem do driver pode citar host e usuario.
        tipo = type(getattr(exc, "orig", None) or exc).__name__
        corpo = FrescorOut(estado="indisponivel", saudavel=False)
        return JSONResponse(status_code=503,
                            content={**jsonable_encoder(corpo), "erro": tipo})
    corpo = FrescorOut(**asdict(frescor), saudavel=frescor.saudavel)
    codigo = 503 if frescor.estado in ESTADOS_COM_PROBLEMA else 200
    return JSONResponse(status_code=codigo, content=jsonable_encoder(corpo))
