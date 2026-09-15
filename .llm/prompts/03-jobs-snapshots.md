# Prompt 03 — Schema histórico: jobs e snapshots

**Entrega:** existe uma identidade única de vaga (`jobs`) e uma linha do tempo de estados observados (`job_snapshots`).

> **O ponto central:** mesma vaga não é o mesmo que mesmo dado. Uma vaga pode continuar aberta e mudar descrição, modalidade ou localização; apagar o estado anterior destrói a pergunta mais interessante do projeto: “o que mudou ao longo do tempo?”

---

## O que mostrar antes

Mostre o `Job` usado hoje pelo scraper e a migration anterior. Ainda não conecte o scraper ao banco: primeiro prove que o modelo suporta uma vaga com vários snapshots.

## Contexto e objetivo

Alembic já está integrado. Agora modele a identidade estável de uma vaga separada de seus estados observados ao longo das coletas. Isto preserva histórico: mesma vaga não é duplicata, mas cada coleta pode gerar um snapshot.

## Analise exatamente isto

- `scraper/models.py` e dados que o pipeline já produz.
- Modelos SQLAlchemy existentes, estilo de chaves, datas e serialização da API.
- Migrations anteriores e testes de modelo.

## Implemente somente isto

1. Crie entidade/tabela `jobs` com `id`, `source`, `external_id`, `url`, `first_seen_at`, `last_seen_at`, `is_active`; use restrição única em `(source, external_id)` quando ambos existirem.
2. Crie `job_snapshots` com `id`, `job_id` (FK), `collected_at`, `title`, `company`, `description`, `location`, `workplace_type`, `published_date`, `seniority`, `area`, `area_score` e campos de skills/matches apenas se a convenção atual justificar.
3. Crie relacionamento um-para-muitos e índices para `(job_id, collected_at)` e consultas frequentes.
4. Gere migration Alembic revisada manualmente e atualize a documentação do modelo em `docs/data-model.md`.

## Arquivos/áreas esperados para revisão

Modelos de domínio e ORM, `migrations/versions/`, testes de banco/modelos, documentação.

## Tecnologias envolvidas

SQLAlchemy, Alembic, PostgreSQL/Neon.

## Como verificar a entrega

1. Inserir duas observações da mesma vaga cria um único `jobs` e dois `job_snapshots` ligados por FK.
2. Inserir novamente a mesma combinação `source + external_id` em `jobs` falha/é impedido pela constraint.
3. A migration mostra explicitamente FKs, índices e a reversão possível.

## Armadilha importante

Não copie todos os campos de snapshot para `jobs`. `jobs` é identidade e ciclo de vida; detalhes que podem mudar pertencem ao snapshot.

## Restrições

- Não conecte o scraper/pipeline à gravação ainda.
- Não use CSV como entrada nesta etapa.
- Não guarde segredos nem substitua automaticamente registros históricos.

## Testes

Em banco isolado, valide FKs, unicidade `(source, external_id)`, criação de múltiplos snapshots para a mesma vaga e timestamps/campos obrigatórios. Rode toda a suíte.

## Critérios de conclusão

- Uma vaga tem identidade única e diversos snapshots temporais.
- Migration sobe e desce de modo seguro em ambiente de teste.
- Modelo e diagrama/descrição estão documentados.

## Encerramento obrigatório

Apresente schema, migration e testes. **PARE. Não implemente ingestão, idempotência operacional, Actions ou dashboard.**
