# Prompt 02 — Alembic e base de migrations

**Entrega:** migrations versionadas podem preparar o schema de modo repetível, lendo a configuração centralizada e sem depender de cliques no banco.

> **Por que importa:** uma alteração de banco que só existe na sua máquina não é arquitetura; é uma instrução esquecível. A migration transforma a mudança em código revisável.

---

## O que mostrar antes

Mostre onde está a metadata SQLAlchemy e que ainda não existem as tabelas históricas novas. Esta etapa instala o trilho; a próxima põe os dados nele.

## Contexto e objetivo

Com `DATABASE_URL` centralizada, precisamos introduzir migrations reprodutíveis. Esta etapa instala e integra Alembic à configuração existente; ainda não define o modelo histórico `jobs`/`job_snapshots`.

## Analise exatamente isto

- Configuração SQLAlchemy e localização de `Base`/metadata.
- Convenções de dependências e testes do repositório.
- `docs/neon-setup.md` e baseline para não quebrar API ou Docker atuais.

## Implemente somente isto

1. Adicione Alembic às dependências e inicialize a estrutura de migrations na localização mais coerente com o projeto.
2. Configure `alembic.ini`/`env.py` para obter a URL pelo módulo de configuração, nunca por credencial embutida.
3. Faça a metadata dos modelos SQLAlchemy ser descoberta corretamente por autogenerate, sem duplicar modelos.
4. Crie documentação curta `docs/migrations.md` com comandos para gerar, revisar, aplicar e reverter migrations, destacando revisão humana do SQL gerado.
5. Se já houver schema legado sem migration, crie apenas uma migration de baseline compatível após inspecionar o banco/modelos; não redesenhe tabelas.

## Arquivos/áreas esperados para revisão

Modelos SQLAlchemy, módulo de configuração, requirements, `alembic.ini`, diretório `migrations/` e documentação.

## Tecnologias envolvidas

Alembic, SQLAlchemy e PostgreSQL/Neon.

## Como verificar a entrega

1. O comando de validação/configuração Alembic encontra a metadata sem URL fixa no arquivo.
2. Em banco isolado, `upgrade` aplica a baseline e `downgrade` a reverte quando aplicável.
3. `docs/migrations.md` mostra a ordem: gerar, revisar SQL, aplicar e reverter.

## Armadilha importante

Autogenerate não substitui revisão humana: confira constraints, índices e qualquer operação destrutiva antes de aplicar uma migration.

## Restrições

- Não criar ainda `jobs` ou `job_snapshots` novos.
- Não executar migration contra Neon real sem uma `DATABASE_URL` explicitamente fornecida pelo operador.
- Não apagar tabelas existentes ou recriar banco.

## Testes

Teste que o ambiente Alembic carrega a configuração sem segredos. Em banco efêmero/isolado quando a infraestrutura já permitir, valide `upgrade` e `downgrade` da baseline. Execute pytest.

## Critérios de conclusão

- Migrations são versionadas e usam a configuração centralizada.
- Há procedimento documentado e reversível.
- Nenhuma mudança no domínio histórico foi adiantada.

## Encerramento obrigatório

Mostre migration(s), comandos validados e resultado dos testes. **PARE. Não implemente jobs/snapshots nem persistência.**
