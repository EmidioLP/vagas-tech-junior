"""Reclassifica a area (e infere a modalidade ausente) dos snapshots com as regras atuais.

A area de cada snapshot foi gravada com as regras vigentes na coleta. Quando
`scraper/rules/areas.yml` muda, o passado fica com a classificacao antiga: a
serie historica do dashboard mostraria areas velhas nos dias antigos e novas nos
recentes, e as checagens de qualidade acusariam area fora do dominio nas vagas
que ficaram com um nome de area que nao existe mais.

Este script refaz a classificacao a partir de `title` + `description`, que e
exatamente o que o classificador le, e **recalcula o `content_hash`**.

O mesmo vale para `scraper/rules/modalidade.yml`: snapshots gravados sem
modalidade (nulo ou "Não informado") recebem a modalidade inferida de
`title` + `description` + `location`. Modalidade ja informada nunca muda. As
vagas antigas do LinkedIn nao tem descricao gravada, entao para elas so o
titulo e o local contam. Sem
recalcular, a coleta seguinte compararia a assinatura nova (area nova) com a
gravada (area velha), veria diferenca e gravaria um snapshot novo para cada
vaga -- uma mudanca de estado que nunca aconteceu.

    python scripts/reclassificar_areas.py            # simula e relata
    python scripts/reclassificar_areas.py --aplicar  # grava
    python scripts/reclassificar_areas.py --db data/teste.db --aplicar

**Escreve no banco.** Antes de rodar com `--aplicar` na `dados-main`, crie a
branch de backup no Neon (`docs/neon-setup.md`). Nada e apagado: so as colunas
`area`, `area_score`, `area_matches`, `workplace_type` e `content_hash` de
`job_snapshots` mudam.

Antes de qualquer escrita o script confere que consegue **reproduzir** o
`content_hash` ja gravado a partir dos campos do snapshot. Se um unico hash nao
bater, a reconstrucao esta errada e nada e gravado.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@dataclass
class Plano:
    """O que a reclassificacao faria. Montado sem gravar nada."""

    snapshots: int = 0
    mudam: int = 0
    antes: Counter = field(default_factory=Counter)
    depois: Counter = field(default_factory=Counter)
    # Area atual de cada vaga (ultimo snapshot), que e o que API e dashboard mostram.
    vagas_antes: Counter = field(default_factory=Counter)
    vagas_depois: Counter = field(default_factory=Counter)
    fora_do_vocabulario: Counter = field(default_factory=Counter)
    # Modalidade atual de cada vaga, antes e depois da inferencia.
    modalidade_antes: Counter = field(default_factory=Counter)
    modalidade_depois: Counter = field(default_factory=Counter)


def _campos(snapshot) -> dict:
    """Os mesmos campos que `persistence/assinatura.py` resume."""
    return {
        "title": snapshot.title,
        "company": snapshot.company,
        "description": snapshot.description,
        "location": snapshot.location,
        "workplace_type": snapshot.workplace_type,
        "published_date": snapshot.published_date,
        "seniority": snapshot.seniority,
        "area": snapshot.area,
        "area_score": snapshot.area_score,
        "area_matches": snapshot.area_matches,
        "tecnologias": [t.nome for t in snapshot.tecnologias],
    }


def conferir_assinaturas(snapshots) -> list[int]:
    """Ids dos snapshots cujo `content_hash` nao se reproduz a partir dos campos.

    E a garantia de que este script entende a assinatura do mesmo jeito que a
    persistencia. Qualquer divergencia aqui invalida a reclassificacao inteira.
    """
    from persistence.assinatura import assinatura_snapshot

    return [s.id for s in snapshots if assinatura_snapshot(_campos(s)) != s.content_hash]


@dataclass
class Alteracao:
    """Os campos novos de um snapshot, com a assinatura ja recalculada."""

    snapshot_id: int
    area: str
    area_score: float
    area_matches: str
    workplace_type: str | None
    content_hash: str


def _modalidade_nova(snapshot, inferidor) -> str | None:
    """Modalidade inferida so onde falta; a informada fica como esta."""
    from scraper.modalidade import sem_modalidade

    atual = snapshot.workplace_type
    if not sem_modalidade(atual):
        return atual
    inferida = inferidor.inferir(snapshot.title or "", snapshot.description or "",
                                 snapshot.location or "")
    return atual if sem_modalidade(inferida) else inferida


def montar_plano(snapshots, clf, inferidor=None) -> tuple[Plano, list[Alteracao]]:
    """Calcula a area e a modalidade novas de cada snapshot. Nao grava."""
    from persistence.assinatura import assinatura_snapshot

    from api.vocabulary import areas as vocabulario
    from scraper.models import NAO_INFORMADO
    from scraper.modalidade import default_inferidor

    inferidor = inferidor or default_inferidor()

    conhecidas = set(vocabulario())
    plano = Plano(snapshots=len(snapshots))
    alteracoes = []
    # Ultimo snapshot de cada vaga: e dele que sai a "foto atual".
    ultimo: dict[int, object] = {}

    for s in snapshots:
        resultado = clf.classify(s.title or "", s.description or "")
        modalidade = _modalidade_nova(s, inferidor)
        plano.antes[s.area or "(sem area)"] += 1
        plano.depois[resultado.area] += 1
        if s.area and s.area not in conhecidas:
            plano.fora_do_vocabulario[s.area] += 1

        anterior = ultimo.get(s.job_id)
        if anterior is None or s.collected_at > anterior[0].collected_at:
            ultimo[s.job_id] = (s, resultado.area, modalidade)

        matches = "; ".join(resultado.matches)
        if (s.area != resultado.area or (s.area_matches or "") != matches
                or s.workplace_type != modalidade):
            campos = _campos(s)
            campos.update(area=resultado.area, area_score=resultado.score,
                          area_matches=matches, workplace_type=modalidade)
            alteracoes.append(Alteracao(s.id, resultado.area, resultado.score, matches,
                                        modalidade, assinatura_snapshot(campos)))
            plano.mudam += 1

    for snapshot, area_nova, modalidade_nova in ultimo.values():
        plano.vagas_antes[snapshot.area or "(sem area)"] += 1
        plano.vagas_depois[area_nova] += 1
        plano.modalidade_antes[snapshot.workplace_type or NAO_INFORMADO] += 1
        plano.modalidade_depois[modalidade_nova or NAO_INFORMADO] += 1
    return plano, alteracoes


def _tabela(titulo: str, antes: Counter, depois: Counter, rotulo: str = "area") -> None:
    print(f"\n{titulo}")
    print(f"  {rotulo:30s} {'antes':>6s} {'depois':>7s}  {'':>6s}")
    for area in sorted(set(antes) | set(depois), key=lambda a: -depois.get(a, 0)):
        a, d = antes.get(area, 0), depois.get(area, 0)
        seta = "" if a == d else f"{d - a:+d}"
        print(f"  {area:30s} {a:6d} {d:7d}  {seta:>6s}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", help="URL ou caminho SQLite. Sem isso: DATABASE_URL.")
    ap.add_argument("--aplicar", action="store_true",
                    help="grava as mudancas (sem isso, so simula e relata)")
    args = ap.parse_args(argv)

    from sqlalchemy import select
    from sqlalchemy.orm import Session, selectinload

    from api.database import make_engine
    from api.models import JobSnapshot
    from scraper.classifier import default_classifier
    from scraper.config import ConfiguracaoError

    try:
        engine = make_engine(args.db)
    except ConfiguracaoError as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 2

    try:
        with Session(engine) as db:
            snapshots = db.scalars(
                select(JobSnapshot).options(selectinload(JobSnapshot.tecnologias))
                .order_by(JobSnapshot.job_id, JobSnapshot.collected_at)
            ).all()

            if not snapshots:
                print("Nenhum snapshot no banco. Nada a fazer.")
                return 0

            divergentes = conferir_assinaturas(snapshots)
            if divergentes:
                print(f"Erro: {len(divergentes)} de {len(snapshots)} snapshots tem "
                      "content_hash que nao se reproduz a partir dos campos gravados.\n"
                      "A reclassificacao recalcularia o hash errado. Nada foi gravado.",
                      file=sys.stderr)
                return 3

            plano, alteracoes = montar_plano(snapshots, default_classifier())

            print(f"{plano.snapshots} snapshots conferidos, assinatura reproduzida em todos.")
            print(f"{plano.mudam} snapshot(s) mudariam de area, de evidencia ou de modalidade.")
            if plano.fora_do_vocabulario:
                print("\nAreas gravadas que nao existem mais em areas.yml "
                      "(disparam alerta alto de qualidade ate serem reclassificadas):")
                for area, n in plano.fora_do_vocabulario.most_common():
                    print(f"  {n:6d}  {area}")

            _tabela("Por snapshot (historico inteiro):", plano.antes, plano.depois)
            _tabela("Por vaga, pelo snapshot mais recente (o que API e dashboard mostram):",
                    plano.vagas_antes, plano.vagas_depois)
            _tabela("Modalidade por vaga, pelo snapshot mais recente:",
                    plano.modalidade_antes, plano.modalidade_depois, "modalidade")

            if not args.aplicar:
                print("\nSimulacao. Nada foi gravado. Use --aplicar para gravar.")
                return 0

            por_id = {s.id: s for s in snapshots}
            # `db.begin()` nao serve aqui: a leitura acima ja abriu a
            # transacao da sessao. Um commit so no fim: ou tudo muda, ou nada.
            for alteracao in alteracoes:
                s = por_id[alteracao.snapshot_id]
                s.area = alteracao.area
                s.area_score = alteracao.area_score
                s.area_matches = alteracao.area_matches
                s.workplace_type = alteracao.workplace_type
                s.content_hash = alteracao.content_hash
            db.commit()
            print(f"\nGravado: {len(alteracoes)} snapshot(s) atualizados.")
            return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
