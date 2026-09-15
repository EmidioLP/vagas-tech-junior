# Migrations (Alembic)

O schema do banco é versionado em `migrations/versions/`. Toda mudança de tabela
vira um arquivo revisável: nada é criado "no clique" no console do Neon.

## De onde vem a URL

O `alembic.ini` **não tem URL**. `migrations/env.py` a obtém de
`scraper/config.py` (`obter_url_migrations`), procurando nesta ordem:

1. variáveis já definidas no ambiente;
2. `.env.local`, gerado por `neon env pull --service postgres`;
3. `.env`, legado.

A primeira fonte que define `DATABASE_URL_UNPOOLED` ou `DATABASE_URL` decide, e
dentro dela a **conexão direta** (`DATABASE_URL_UNPOOLED`) tem preferência.

**Por que a direta:** no Neon, `DATABASE_URL` passa pelo PgBouncer em modo
transação. DDL e estado de sessão quebram ali com erros que não mencionam o
pooler (`prepared statement already exists`, `relation does not exist`). A API
continua usando a `DATABASE_URL` pooled.

Sem nenhuma das duas, o Alembic falha com `ConfiguracaoError` antes de conectar,
e a mensagem nunca mostra a URL.

**Nunca rode migrations na branch Neon `production`.** Use a branch da feature
ou uma branch temporária (abaixo).

## Fluxo: gerar → revisar → aplicar → reverter

### 1. Gerar

Altere os modelos em `api/models.py` e gere a migration comparando com o banco
atual:

```bash
alembic revision --autogenerate -m "descreve a mudanca"
```

O arquivo sai em `migrations/versions/AAAAMMDD_<rev>_<slug>.py`.

### 2. Revisar (obrigatório)

**Autogenerate não substitui revisão humana.** Abra o arquivo e confira:

- **Constraints:** unique, FK (inclusive `ondelete`), `nullable`, nomes explícitos
  que já existem nos bancos.
- **Índices:** criados e removidos que você esperava, sem duplicatas.
- **Operações destrutivas:** `drop_table`, `drop_column`, mudança de tipo que
  trunca dado. Renomear aparece como *drop + add* e **perde os dados**: reescreva
  como `op.alter_column(..., new_column_name=...)`.
- **`downgrade`:** existe, desfaz exatamente o `upgrade` e na ordem inversa.
- **Portabilidade:** nada específico de SQLite. O banco real é PostgreSQL.

Depois leia o SQL que será executado, **sem conectar ao banco**:

```bash
alembic upgrade head --sql
```

### 3. Aplicar

```bash
alembic upgrade head
alembic current      # revisão aplicada
alembic check        # modelos e banco sem diferença
```

### 4. Reverter

```bash
alembic downgrade -1     # desfaz a última migration
alembic history          # lista as revisões (não conecta)
```

`alembic downgrade base` desfaz **todas** as migrations e **apaga as tabelas**.
Use só em banco isolado.

## Bancos criados antes do Alembic

A API (`init_db`) e o importador ainda criam tabelas com `create_all`. Um banco
criado assim já tem o schema da baseline, mas não tem a tabela `alembic_version`.
Para adotá-lo sem recriar nada:

```bash
alembic stamp head   # só registra a revisão, não altera tabelas
alembic check        # precisa terminar sem diferenças
```

Rode `stamp` **só** quando o schema já corresponde aos modelos. A suíte garante
essa paridade: `tests/api/test_migrations.py` roda `check` depois do `upgrade` e
depois de `create_all` + `stamp`. Se você mudar um modelo sem gerar migration, o
teste falha.

## Testar numa branch Neon temporária

Para validar uma migration no PostgreSQL real sem tocar a branch da feature:

```powershell
# Branch descartável, com expiração automática como rede de segurança
neon branches create --name mig-test --parent feature-data-platform --expires-at <ISO-8601> --no-secrets

# Variáveis dela num arquivo fora do repositório
neon env pull --branch mig-test --service postgres --file <fora-do-repo>/mig-test.env
```

Carregue `DATABASE_URL_UNPOOLED` desse arquivo **só no ambiente do comando**. O
ambiente vence o `.env.local`, então a branch da feature não é usada. Depois:

```bash
alembic upgrade head
alembic check
alembic downgrade base
```

E limpe tudo:

```powershell
neon branches delete mig-test
```

Apague também o arquivo `.env` temporário. Nunca cole a URL em logs, issues ou
documentação.

## Testes

```bash
python -m pytest tests/api/test_migrations.py -q
```

Rodam em SQLite temporário, sem rede. Cobrem:

- `alembic.ini` sem URL;
- URL vinda da configuração central, sem vazar senha no SQL gerado;
- falha clara sem URL;
- `upgrade` → `check` → `downgrade` da baseline;
- `stamp` de um banco criado por `create_all`.
