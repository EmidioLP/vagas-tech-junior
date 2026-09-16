"""Schemas Pydantic (respostas da API).

A API e somente leitura: os dados vem do pipeline de raspagem, entao nao ha
schema de escrita. Cada vaga e uma vaga unica de `jobs` com o estado do snapshot
mais recente (`persistence/foto_atual.py`).
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _TecnologiasComoNomes(BaseModel):
    """Serializa a relacao de tecnologias como uma lista simples de nomes.

    Aceita objetos `Tecnologia` ou nomes (a consulta ja entrega nomes); na
    resposta da API interessa so `["Python", "SQL"]`.
    """

    @field_validator("tecnologias", mode="before", check_fields=False)
    @classmethod
    def _apenas_nomes(cls, value):
        if value is None:
            return []
        return sorted(getattr(item, "nome", item) for item in value)


class TecnologiaResumo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    nome: str = Field(examples=["Python"])
    grupo: str = Field(examples=["linguagens"])


class VagaOut(_TecnologiasComoNomes):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="Id da vaga única (`jobs.id`), estável entre coletas.")
    source: str = Field(description="Portal de origem.", examples=["gupy"])
    external_id: str = Field(description="Id da vaga no portal de origem.")
    title: str
    company: str | None = None
    area: str = Field(examples=["Data"])
    seniority: str | None = Field(default=None, examples=["Júnior"])
    location: str | None = None
    workplace_type: str | None = Field(default=None, examples=["Remoto"])
    published_date: date | None = Field(
        default=None,
        description="Data de publicação normalizada. Nula quando o portal não informa.",
    )
    url: str | None = None
    description: str | None = None
    area_score: float | None = None
    area_matches: str | None = Field(
        default=None,
        description="Keywords que dispararam a classificação, para auditoria.",
    )
    tecnologias: list[str] = Field(
        default_factory=list, examples=[["Python", "SQL"]],
        description="Tecnologias citadas no estado mais recente da vaga.",
    )
    ativa: bool = Field(description="Falso quando a vaga foi encerrada (sumiu do portal).")
    first_seen_at: datetime = Field(description="Primeira coleta em que a vaga apareceu (UTC).")
    last_seen_at: datetime = Field(description="Última coleta em que a vaga apareceu (UTC).")
    closed_at: datetime | None = Field(
        default=None, description="Quando a vaga foi encerrada (UTC). Nulo se ativa.",
    )


class VagaResumo(_TecnologiasComoNomes):
    """Versao enxuta usada na listagem -- sem a descricao inteira."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    external_id: str
    title: str
    company: str | None = None
    area: str
    seniority: str | None = None
    location: str | None = None
    workplace_type: str | None = None
    published_date: date | None = None
    url: str | None = None
    tecnologias: list[str] = Field(default_factory=list)
    ativa: bool


class VagaPage(BaseModel):
    """Envelope da listagem paginada."""

    total: int = Field(description="Total de vagas únicas que casam com os filtros.")
    limit: int
    offset: int
    items: list[VagaResumo]


class AreaOut(BaseModel):
    area: str = Field(examples=["Suporte/Infra"])
    vagas: int = Field(description="Vagas ativas classificadas nesta área (estado atual).")
    percentual: float = Field(description="Percentual sobre o total de vagas ativas.")


class TecnologiaOut(BaseModel):
    nome: str = Field(examples=["Python"])
    grupo: str = Field(examples=["linguagens"])
    vagas: int = Field(description="Vagas ativas que citam esta tecnologia (estado atual).")


class FrescorOut(BaseModel):
    """Estado das coletas. Nunca inclui URL, host ou mensagem de erro do banco."""

    estado: str = Field(
        description=(
            "`em_dia`, `vencido` (última coleta completa com mais de 2× o intervalo), "
            "`coleta_parada` (nenhuma execução registrada há mais de 2 dias), "
            "`sem_coleta`, `sem_intervalo` (sem régua para julgar) ou `indisponivel`."
        ),
        examples=["em_dia"],
    )
    saudavel: bool = Field(description="Verdadeiro só quando `estado` é `em_dia`.")
    ultima_coleta: datetime | None = Field(
        default=None, description="Início da última coleta completa bem-sucedida ou parcial (UTC).")
    status_ultima_coleta: str | None = Field(default=None, examples=["success"])
    dias_desde_ultima_coleta: int | None = None
    intervalo_dias: int | None = Field(
        default=None, description="Intervalo X entre coletas, gravado pela execução agendada.")
    limite_dias: int | None = Field(default=None, description="Dias sem coleta completa até vencer (2× X).")
    ultima_execucao: datetime | None = Field(
        default=None, description="Última execução de qualquer status, inclusive pulada (UTC).")
    status_ultima_execucao: str | None = Field(default=None, examples=["skipped"])
    dias_desde_ultima_execucao: int | None = None
    proxima_coleta: date | None = Field(default=None, description="Próxima coleta prevista (UTC).")


class Erro(BaseModel):
    detail: str
