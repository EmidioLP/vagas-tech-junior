# Prompt 13 — Arquitetura e registro de decisões

**Entrega:** um leitor entende em poucos minutos o fluxo real do projeto, por que cada peça existe e o que foi deliberadamente deixado de fora, sem precisar ler o código.

> **Para portfólio:** "não usei Airflow porque o GitHub Actions já agenda, isola fontes e registra execuções para 600 vagas a cada 2 dias" mostra mais critério do que uma lista longa de ferramentas.

---

## O que mostrar antes

Pegue três afirmações do README (fluxo de dados, onde a API lê, como a coleta é agendada) e confira cada uma contra código, workflow ou migration. Só entra na documentação o que o repositório faz hoje.

## Contexto e objetivo

O produto está completo: coleta agendada, modelo histórico, qualidade, frescor, API e dashboard publicados. A documentação cresceu por etapa e está espalhada. Consolide arquitetura e decisões sem duplicar o que já está bem documentado.

## Analise exatamente isto

- README (hoje com mais de 800 linhas), `CLAUDE.md` e todos os arquivos de `docs/`.
- `scraper/pipeline.py`, `persistence/`, `api/`, `dashboard/`, workflows, `render.yaml` e `docs/roadmap-status.md`.

## Implemente somente isto

1. `docs/architecture.md`: diagrama Mermaid do fluxo (portais → coleta no Actions → filtros/classificação → Neon `jobs`/`job_snapshots`/`collection_runs` → API no Render e dashboard no Streamlit), com uma frase por componente e links para os docs detalhados.
2. `docs/decisoes/` com ADRs curtos (contexto, decisão, consequências):
   - Neon com branches;
   - `jobs` + snapshots por hash;
   - GitHub Actions em vez de Airflow;
   - sem camadas Bronze/Silver/Gold nem dbt no volume atual, e o que mudaria essa decisão;
   - Render + Streamlit Community Cloud;
   - checagens de qualidade em Python em vez de ferramenta dedicada.
3. README: mantenha propósito, achados datados, links publicados e quickstart; mova detalhes extensos (ex.: seções longas por portal) para `docs/` quando isso deixar o README mais legível, sem perder conteúdo.
4. Seção de limitações: éticas e técnicas do scraping, fontes bloqueadas, frequência, viés das fontes grandes e mudança de regras de classificação ao longo do histórico.
5. Atualize `docs/roadmap-status.md` e `CLAUDE.md` para refletirem a estrutura final.

## Arquivos/áreas esperados para revisão

README, `CLAUDE.md` e `docs/`; código só para confirmar fatos.

## Tecnologias envolvidas

Markdown, Mermaid.

## Como verificar a entrega

1. O diagrama bate com o código: cada seta corresponde a um módulo, workflow ou tabela real.
2. Todo link interno aponta para arquivo e seção existentes.
3. Um leitor sem acesso a segredos consegue rodar o quickstart local (`--no-db --csv` ou Compose) sem adivinhar nada.
4. Cada ADR tem contexto, decisão e consequência, incluindo o custo da decisão.

## Armadilha importante

Não reescreva números atuais no README; eles vivem no dashboard e em relatórios datados. Não chame de "em produção" nada que não esteja publicado e verificável por link.

## Restrições

- Não implemente código ou infraestrutura.
- Não declare métricas, integrações ou deploys que não existem.
- Não apague conteúdo técnico útil; mova e linke.

## Testes

Verifique links internos, blocos Mermaid e comandos do quickstart. Rode a suíte, porque há testes que fixam trechos de docs e configuração.

## Critérios de conclusão

- Arquitetura, decisões e limites são compreensíveis e fiéis ao repositório.
- O README ficou mais curto sem perder informação.

## Encerramento obrigatório

Liste documentos criados/movidos e as verificações feitas. **PARE. Não faça a auditoria final nem correções de código.**
